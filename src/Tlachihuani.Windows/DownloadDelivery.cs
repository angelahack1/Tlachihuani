// Tlachihuani — Angela López Mendoza · XAIHT
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.ComponentModel;
using Microsoft.Win32.SafeHandles;

namespace Tlachihuani.Windows;

public static class DownloadDelivery
{
    private static readonly Guid Downloads = new("374DE290-123F-4565-9164-39C4925E467B");

    [DllImport("shell32.dll", ExactSpelling = true)]
    private static extern int SHGetKnownFolderPath(in Guid folder, uint flags, IntPtr token, out IntPtr path);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
    private static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security,
        uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandleW(SafeFileHandle file, StringBuilder path, uint capacity, uint flags);

    private static string FinalDirectory(string path)
    {
        // Follow links, then compare the actual directory with the proposed path.
        // The service has rights to the leaf, not to enumerate the user's parents.
        using var file = CreateFileW(Path.GetFullPath(path), 0x80 /* FILE_READ_ATTRIBUTES */, 7,
            IntPtr.Zero, 3 /* OPEN_EXISTING */, 0x02000000 /* FILE_FLAG_BACKUP_SEMANTICS */, IntPtr.Zero);
        if (file.IsInvalid) throw new IOException("Cannot open the account download folder.", new Win32Exception(Marshal.GetLastWin32Error()));
        var result = new StringBuilder(32768);
        uint count = GetFinalPathNameByHandleW(file, result, (uint)result.Capacity, 0);
        if (count == 0 || count >= result.Capacity)
            throw new IOException("Cannot verify the account download folder's final path.", new Win32Exception(Marshal.GetLastWin32Error()));
        var final = result.ToString();
        if (final.StartsWith(@"\\?\UNC\", StringComparison.OrdinalIgnoreCase)) return @"\\" + final[8..];
        return final.StartsWith(@"\\?\", StringComparison.Ordinal) ? final[4..] : final;
    }

    // Resolve from the authenticated user's token, never a browser-provided path.
    public static string Root(WindowsIdentity user, string profile)
    {
        if (profile.Length > 128) throw new InvalidDataException("Invalid profile.");
        Marshal.ThrowExceptionForHR(SHGetKnownFolderPath(in Downloads, 0x4000, user.AccessToken.DangerousGetHandle(), out var raw));
        string downloads;
        try { downloads = Marshal.PtrToStringUni(raw) ?? throw new IOException("Downloads is unavailable."); }
        finally { Marshal.FreeCoTaskMem(raw); }
        return Path.Combine(downloads, "Torrenter", ProfileDirectory(user.User!.Value, profile));
    }

    private static string ProfileDirectory(string sid, string profile) =>
        profile.StartsWith("tlm-", StringComparison.Ordinal) && Guid.TryParse(profile[4..], out var account)
            ? account.ToString("N")
            : Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(sid + "/" + profile)));

    // The pipe intentionally supplies an identification-only token. Validate the
    // controller-created folder under the service identity instead of requesting
    // impersonation privileges. The caller must own it; REST cannot enter here.
    public static string Validate(string? path, string sid, string profile, bool fallback = false)
    {
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path) || profile.Length > 128)
            throw new IOException("The local controller has not prepared Windows Downloads.");
        var folder = new DirectoryInfo(path);
        if (!folder.Exists || folder.Name != ProfileDirectory(sid, profile) || folder.Parent?.Name != "Torrenter")
            throw new IOException("Unexpected account download folder.");
        if (fallback && !string.Equals(folder.Parent?.Parent?.Name, "content_generated", StringComparison.OrdinalIgnoreCase))
            throw new IOException("Unexpected generated content folder.");
        if ((folder.Attributes & FileAttributes.ReparsePoint) != 0 ||
            !string.Equals(FinalDirectory(folder.FullName), folder.FullName, StringComparison.OrdinalIgnoreCase))
            throw new IOException("The delivery destination contains a reparse point.");
        if (folder.GetAccessControl(AccessControlSections.Owner).GetOwner(typeof(SecurityIdentifier))?.Value != sid)
            throw new UnauthorizedAccessException("The download folder must belong to the requesting Windows user.");
        return folder.FullName;
    }

    // This runs in the ordinary local controller, before entering the native pipe.
    // Keep the pipe identification-only; the service never impersonates a client
    // for file writes and receives no broader rights over Windows Downloads.
    public static string Prepare(WindowsIdentity user, string profile, bool development, string? contentRoot = null)
    {
        if (contentRoot is not null && (!Path.IsPathFullyQualified(contentRoot)
            || !string.Equals(Path.GetFileName(contentRoot), "content_generated", StringComparison.OrdinalIgnoreCase)
            || !string.Equals(Path.GetFullPath(contentRoot), contentRoot, StringComparison.OrdinalIgnoreCase)))
            throw new IOException("Invalid generated content folder.");
        var directory = new DirectoryInfo(contentRoot is null ? Root(user, profile)
            : Path.Combine(contentRoot, "Torrenter", ProfileDirectory(user.User!.Value, profile)));
        for (var part = directory; part is not null; part = part.Parent)
            if (part.Exists && (part.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new IOException("The download destination contains a reparse point.");
        directory.Create();
        Validate(directory.FullName, user.User!.Value, profile, fallback: contentRoot is not null);
        if (!development)
        {
            var service = (SecurityIdentifier)new NTAccount("NT SERVICE", "Tlachihuani.Jobs").Translate(typeof(SecurityIdentifier));
            var acl = directory.GetAccessControl();
            acl.SetAccessRule(new FileSystemAccessRule(service, FileSystemRights.Modify,
                InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
                PropagationFlags.None, AccessControlType.Allow));
            directory.SetAccessControl(acl);
        }
        return directory.FullName;
    }
}
