// Tlachihuani — Angela López Mendoza · XAIHT
using System.Security.AccessControl;
using System.Security.Principal;
using Tlachihuani.Windows;

internal static class DownloadAccessChecks
{
    public static int Run()
    {
        using var user = WindowsIdentity.GetCurrent();
        var sid = user.User!;
        var profile = Guid.NewGuid();
        var scratch = Directory.CreateTempSubdirectory("jobs-delivery-acl-");
        var parent = scratch.CreateSubdirectory("Torrenter");
        var leaf = parent.CreateSubdirectory(profile.ToString("N"));
        var deny = new FileSystemAccessRule(sid, FileSystemRights.ListDirectory | FileSystemRights.ReadAttributes,
            InheritanceFlags.None, PropagationFlags.None, AccessControlType.Deny);
        var acl = parent.GetAccessControl(AccessControlSections.Access);
        acl.AddAccessRule(deny);
        try
        {
            parent.SetAccessControl(acl);
            bool denied = false;
            try { _ = parent.GetFileSystemInfos(); } catch (UnauthorizedAccessException) { denied = true; }
            if (!denied) throw new InvalidOperationException("The real parent ACL did not restrict enumeration.");
            var validated = DownloadDelivery.Validate(leaf.FullName, sid.Value, "tlm-" + profile);
            if (validated != leaf.FullName) throw new InvalidOperationException("Unexpected validated folder.");
            bool refused = false;
            try { DownloadDelivery.Validate(leaf.FullName, new SecurityIdentifier(WellKnownSidType.WorldSid, null).Value, "tlm-" + profile); }
            catch (UnauthorizedAccessException) { refused = true; }
            if (!refused) throw new InvalidOperationException("Wrong Windows owner accepted.");
            Console.WriteLine("PASS: restricted parent, accessible account directory, and wrong-owner refusal (real Windows ACLs).");
            return 0;
        }
        finally
        {
            acl.RemoveAccessRuleSpecific(deny);
            parent.SetAccessControl(acl);
            leaf.Delete(); parent.Delete(); scratch.Delete();
        }
    }
}
