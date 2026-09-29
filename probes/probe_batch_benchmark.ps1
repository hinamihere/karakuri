$source = @"
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Karakuri.Probe
{
    [ComImport]
    [Guid("ff48dba4-60ef-4201-aa87-54103eef594e")]
    public class CUIAutomationClass {}

    [ComImport]
    [Guid("30cbe57d-d9d0-452a-ab13-7ac5ac4825ee")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IUIAutomation
    {
        void CompareElements(IUIAutomationElement el1, IUIAutomationElement el2, out int areSame);
        void CompareRuntimeIds(IntPtr r1, IntPtr r2, out int areSame);
        void GetRootElement(out IUIAutomationElement root);
        void ElementFromHandle(IntPtr hwnd, out IUIAutomationElement element);
        void ElementFromPoint(tagPOINT pt, out IUIAutomationElement element);
        void GetFocusedElement(out IUIAutomationElement element);
        void GetRootElementBuildCache(IUIAutomationCacheRequest cacheRequest, out IUIAutomationElement root);
        void ElementFromHandleBuildCache(IntPtr hwnd, IUIAutomationCacheRequest cacheRequest, out IUIAutomationElement element);
        void ElementFromPointBuildCache(tagPOINT pt, IUIAutomationCacheRequest cacheRequest, out IUIAutomationElement element);
        void GetFocusedElementBuildCache(IUIAutomationCacheRequest cacheRequest, out IUIAutomationElement element);
        void CreateTreeWalker(IUIAutomationCondition pCondition, out IUIAutomationTreeWalker walker);
        void Get_ControlViewWalker(out IUIAutomationTreeWalker walker);
        void Get_ContentViewWalker(out IUIAutomationTreeWalker walker);
        void Get_RawViewWalker(out IUIAutomationTreeWalker walker);
        void Get_RawViewCondition(out IUIAutomationCondition condition);
        void Get_ControlViewCondition(out IUIAutomationCondition condition);
        void Get_ContentViewCondition(out IUIAutomationCondition condition);
        void CreateCacheRequest(out IUIAutomationCacheRequest cacheRequest);
        void CreateTrueCondition(out IUIAutomationCondition newCondition);
        void CreateFalseCondition(out IUIAutomationCondition newCondition);
        void CreatePropertyCondition(int propertyId, object value, out IUIAutomationCondition newCondition);
        void CreatePropertyConditionEx(int propertyId, object value, PropertyConditionFlags flags, out IUIAutomationCondition newCondition);
        void CreateAndCondition(IUIAutomationCondition c1, IUIAutomationCondition c2, out IUIAutomationCondition newCondition);
        void CreateAndConditionFromArray(IUIAutomationCondition[] conditions, out IUIAutomationCondition newCondition);
        void CreateAndConditionFromNativeArray(IntPtr conditions, int conditionCount, out IUIAutomationCondition newCondition);
        void CreateOrCondition(IUIAutomationCondition c1, IUIAutomationCondition c2, out IUIAutomationCondition newCondition);
        void CreateOrConditionFromArray(IUIAutomationCondition[] conditions, out IUIAutomationCondition newCondition);
        void CreateOrConditionFromNativeArray(IntPtr conditions, int conditionCount, out IUIAutomationCondition newCondition);
        void CreateNotCondition(IUIAutomationCondition condition, out IUIAutomationCondition newCondition);
    }

    [ComImport]
    [Guid("d22108aa-8ac5-49a5-837b-37bbb3d7591e")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IUIAutomationElement
    {
        void SetFocus();
        void GetRuntimeId(out Array runtimeId);
        void FindFirst(TreeScope scope, IUIAutomationCondition condition, out IUIAutomationElement found);
        void FindAll(TreeScope scope, IUIAutomationCondition condition, out IUIAutomationElementArray found);
        void FindFirstBuildCache(TreeScope scope, IUIAutomationCondition condition, IUIAutomationCacheRequest cacheRequest, out IUIAutomationElement found);
        void FindAllBuildCache(TreeScope scope, IUIAutomationCondition condition, IUIAutomationCacheRequest cacheRequest, out IUIAutomationElementArray found);
        void BuildUpdatedCache(IUIAutomationCacheRequest cacheRequest, out IUIAutomationElement updatedElement);
        void GetCurrentPropertyValue(int propertyId, out object value);
        void GetCurrentPropertyValueEx(int propertyId, int ignoreDefaultValue, out object value);
        void GetCachedPropertyValue(int propertyId, out object value);
        void GetCachedPropertyValueEx(int propertyId, int ignoreDefaultValue, out object value);
        void GetCurrentPatternAs(int patternId, [In] ref Guid riid, [MarshalAs(UnmanagedType.IUnknown)] out object patternObject);
        void GetCachedPatternAs(int patternId, [In] ref Guid riid, [MarshalAs(UnmanagedType.IUnknown)] out object patternObject);
        void GetCurrentPattern(int patternId, [MarshalAs(UnmanagedType.IUnknown)] out object patternObject);
        void GetCachedPattern(int patternId, [MarshalAs(UnmanagedType.IUnknown)] out object patternObject);
        void GetCachedParent(out IUIAutomationElement parent);
        void GetCachedChildren(out IUIAutomationElementArray children);
        void Get_CurrentProcessId(out int retVal);
        void Get_CurrentControlType(out int retVal);
        void Get_CurrentLocalizedControlType([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CurrentName([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CurrentAcceleratorKey([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CurrentAccessKey([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CurrentHasKeyboardFocus(out int retVal);
        void Get_CurrentIsKeyboardFocusable(out int retVal);
        void Get_CurrentIsEnabled(out int retVal);
        void Get_CurrentAutomationId([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CurrentClassName([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CurrentHelpText([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CurrentCulture(out int retVal);
        void Get_CurrentIsControlElement(out int retVal);
        void Get_CurrentIsContentElement(out int retVal);
        void Get_CurrentIsPassword(out int retVal);
        void Get_CurrentNativeWindowHandle(out IntPtr retVal);
        void Get_CurrentItemType([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CurrentIsOffscreen(out int retVal);
        void Get_CurrentOrientation(out int retVal);
        void Get_CurrentFrameworkId([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CurrentIsRequiredForForm(out int retVal);
        void Get_CurrentItemStatus([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CurrentBoundingRectangle(out tagRECT retVal);

        void Get_CachedProcessId(out int retVal);
        void Get_CachedControlType(out int retVal);
        void Get_CachedLocalizedControlType([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CachedName([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CachedAcceleratorKey([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CachedAccessKey([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CachedHasKeyboardFocus(out int retVal);
        void Get_CachedIsKeyboardFocusable(out int retVal);
        void Get_CachedIsEnabled(out int retVal);
        void Get_CachedAutomationId([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CachedClassName([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CachedHelpText([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CachedCulture(out int retVal);
        void Get_CachedIsControlElement(out int retVal);
        void Get_CachedIsContentElement(out int retVal);
        void Get_CachedIsPassword(out int retVal);
        void Get_CachedNativeWindowHandle(out IntPtr retVal);
        void Get_CachedItemType([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CachedIsOffscreen(out int retVal);
        void Get_CachedOrientation(out int retVal);
        void Get_CachedFrameworkId([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CachedIsRequiredForForm(out int retVal);
        void Get_CachedItemStatus([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CachedBoundingRectangle(out tagRECT retVal);
    }

    [ComImport]
    [Guid("14314595-b4bc-4055-95f2-58f2e42c9855")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IUIAutomationElementArray
    {
        void Get_Length(out int length);
        void GetElement(int index, out IUIAutomationElement element);
    }

    [ComImport]
    [Guid("352ffba8-0973-437c-a61f-f64cafd81df9")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IUIAutomationCondition {}

    [ComImport]
    [Guid("4042c624-389c-4afc-a630-9df854a541fc")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IUIAutomationTreeWalker {}

    [ComImport]
    [Guid("b32a92b5-bc25-4078-9c08-d7ee95c48e03")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IUIAutomationCacheRequest
    {
        void AddProperty(int propertyId);
        void AddPattern(int patternId);
        void Clone(out IUIAutomationCacheRequest newRequest);
        void Get_TreeScope(out TreeScope scope);
        void Set_TreeScope(TreeScope scope);
        void Get_TreeFilter(out IUIAutomationCondition filter);
        void Set_TreeFilter(IUIAutomationCondition filter);
        void Get_AutomationElementMode(out AutomationElementMode mode);
        void Set_AutomationElementMode(AutomationElementMode mode);
    }

    public enum TreeScope { Element = 1, Children = 2, Descendants = 4, Subtree = 7, Ancestors = 8 }
    public enum AutomationElementMode { None = 0, Full = 1 }
    public enum PropertyConditionFlags { None = 0, IgnoreCase = 1 }

    [StructLayout(LayoutKind.Sequential)]
    public struct tagPOINT { public int x; public int y; }

    [StructLayout(LayoutKind.Sequential)]
    public struct tagRECT { public int left; public int top; public int right; public int bottom; }

    public class BenchmarkRunner
    {
        public static void Run()
        {
            var uia = (IUIAutomation)new CUIAutomationClass();
            Process notepad = Process.Start("notepad.exe");
            System.Threading.Thread.Sleep(800);

            try
            {
                IUIAutomationElement rootElem;
                uia.ElementFromHandle(notepad.MainWindowHandle, out rootElem);
                IUIAutomationCondition trueCond;
                uia.CreateTrueCondition(out trueCond);

                // Prepare CacheRequest
                IUIAutomationCacheRequest cacheReq;
                uia.CreateCacheRequest(out cacheReq);
                cacheReq.AddProperty(30012); // ClassName
                cacheReq.AddProperty(30005); // Name
                cacheReq.AddProperty(30011); // AutomationId
                cacheReq.AddProperty(30003); // ControlType
                cacheReq.AddProperty(30010); // IsEnabled
                cacheReq.AddProperty(30001); // BoundingRectangle
                cacheReq.AddPattern(10002);  // ValuePattern
                cacheReq.AddPattern(10000);  // InvokePattern
                cacheReq.Set_TreeScope(TreeScope.Element);

                int iterations = 20;

                // 1. Un-cached tree traversal: FindAll + query each property
                Console.WriteLine("Starting uncached loop...");
                var swUncached = Stopwatch.StartNew();
                int totalElements = 0;
                for (int iter = 0; iter < iterations; iter++)
                {
                    IUIAutomationElementArray arr;
                    rootElem.FindAll(TreeScope.Descendants, trueCond, out arr);
                    int len;
                    arr.Get_Length(out len);
                    totalElements = len;
                    for (int i = 0; i < len; i++)
                    {
                        IUIAutomationElement el;
                        arr.GetElement(i, out el);
                        string cls, name, autoId;
                        int ct, en;
                        tagRECT rc;
                        el.Get_CurrentClassName(out cls);
                        el.Get_CurrentName(out name);
                        el.Get_CurrentAutomationId(out autoId);
                        el.Get_CurrentControlType(out ct);
                        el.Get_CurrentIsEnabled(out en);
                        el.Get_CurrentBoundingRectangle(out rc);
                    }
                }
                swUncached.Stop();
                long uncachedTime = swUncached.ElapsedMilliseconds;
                Console.WriteLine(string.Format("Uncached finished: {0} ms", uncachedTime));

                // 2. Batched tree traversal: FindAllBuildCache + read from cached memory
                Console.WriteLine("Starting cached loop...");
                var swCached = Stopwatch.StartNew();
                for (int iter = 0; iter < iterations; iter++)
                {
                    IUIAutomationElementArray arr;
                    try {
                        rootElem.FindAllBuildCache(TreeScope.Descendants, trueCond, cacheReq, out arr);
                    } catch (Exception ex) {
                        Console.WriteLine("FindAllBuildCache threw: " + ex.ToString());
                        throw;
                    }
                    int len;
                    arr.Get_Length(out len);
                    for (int i = 0; i < len; i++)
                    {
                        IUIAutomationElement el;
                        arr.GetElement(i, out el);
                        object vCls, vName, vAutoId, vCt, vEn, vRc;
                        el.GetCachedPropertyValue(30012, out vCls);
                        el.GetCachedPropertyValue(30005, out vName);
                        el.GetCachedPropertyValue(30011, out vAutoId);
                        el.GetCachedPropertyValue(30003, out vCt);
                        el.GetCachedPropertyValue(30010, out vEn);
                        el.GetCachedPropertyValue(30001, out vRc);
                    }
                }
                swCached.Stop();
                long cachedTime = swCached.ElapsedMilliseconds;

                Console.WriteLine(string.Format("Tree size: {0} elements", totalElements));
                Console.WriteLine(string.Format("Iterations: {0}", iterations));
                Console.WriteLine(string.Format("Uncached FindAll + per-property round-trips: {0} ms (avg {1:F2} ms/tree dump)",
                    uncachedTime, (double)uncachedTime / iterations));
                Console.WriteLine(string.Format("Batched FindAllBuildCache: {0} ms (avg {1:F2} ms/tree dump)",
                    cachedTime, (double)cachedTime / iterations));
                if (cachedTime > 0)
                {
                    Console.WriteLine(string.Format("Batching Speedup Factor: {0:F2}x faster", (double)uncachedTime / cachedTime));
                }
            }
            finally
            {
                if (!notepad.HasExited) notepad.Kill();
            }
        }
    }
}
"@

Add-Type -TypeDefinition $source -Language CSharp
[Karakuri.Probe.BenchmarkRunner]::Run()
