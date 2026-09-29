# Karakuri Native UIA COM Probe
$code = @"
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Karakuri.Probe
{
    [ComImport]
    [Guid("ff48dba4-60ef-4201-aa87-54103eef594e")]
    [CoClass(typeof(CUIAutomationClass))]
    public interface CUIAutomation : IUIAutomation {}

    [ComImport]
    [Guid("ff48dba4-60ef-4201-aa87-54103eef594e")]
    [ClassInterface(ClassInterfaceType.None)]
    [TypeLibType(TypeLibTypeFlags.FCanCreate)]
    public class CUIAutomationClass {}

    [ComImport]
    [Guid("30cbe57d-d9d0-452a-ab13-7ac0ac4825ee")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IUIAutomation
    {
        // VTable layout for IUIAutomation
        void CompareElements(IntPtr el1, IntPtr el2, out int areSame);
        void CompareRuntimeIds(IntPtr r1, IntPtr r2, out int areSame);
        void GetRootElement(out IntPtr root);
        void ElementFromHandle(IntPtr hwnd, out IntPtr element);
        void ElementFromPoint(tagPOINT pt, out IntPtr element);
        void GetFocusedElement(out IntPtr element);
        void GetRootElementBuildCache(IntPtr cacheRequest, out IntPtr root);
        void ElementFromHandleBuildCache(IntPtr hwnd, IntPtr cacheRequest, out IntPtr element);
        void ElementFromPointBuildCache(tagPOINT pt, IntPtr cacheRequest, out IntPtr element);
        void GetFocusedElementBuildCache(IntPtr cacheRequest, out IntPtr element);
        void CreateTreeWalker(IntPtr pCondition, out IntPtr walker);
        void Get_ControlViewWalker(out IntPtr walker);
        void Get_ContentViewWalker(out IntPtr walker);
        void Get_RawViewWalker(out IntPtr walker);
        void Get_RawViewCondition(out IntPtr condition);
        void Get_ControlViewCondition(out IntPtr condition);
        void Get_ContentViewCondition(out IntPtr condition);
        void CreateCacheRequest(out IntPtr cacheRequest);
        void CreateTrueCondition(out IntPtr newCondition);
        void CreateFalseCondition(out IntPtr newCondition);
        void CreatePropertyCondition(int propertyId, object value, out IntPtr newCondition);
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct tagPOINT
    {
        public int x;
        public int y;
    }

    public class Tester
    {
        public static void Run()
        {
            Console.WriteLine("C# COM interop probe loaded.");
        }
    }
}
"@

Add-Type -TypeDefinition $code -Language CSharp
[Karakuri.Probe.Tester]::Run()
