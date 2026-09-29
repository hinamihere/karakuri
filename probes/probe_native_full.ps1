$source = @"
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Karakuri.Probe
{
    [ComImport]
    [Guid("e22ad333-b25f-460c-83d0-0581107395c9")]
    public class CUIAutomation8Class {}

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
        void AddAutomationEventHandler(int eventId, IUIAutomationElement element, TreeScope scope, IUIAutomationCacheRequest cacheRequest, IntPtr handler);
        void RemoveAutomationEventHandler(int eventId, IUIAutomationElement element, IntPtr handler);
        void AddPropertyChangedEventHandlerNativeArray(IUIAutomationElement element, TreeScope scope, IUIAutomationCacheRequest cacheRequest, IntPtr handler, IntPtr propertyArray, int propertyCount);
        void AddPropertyChangedEventHandler(IUIAutomationElement element, TreeScope scope, IUIAutomationCacheRequest cacheRequest, IntPtr handler, int[] propertyArray);
        void RemovePropertyChangedEventHandler(IUIAutomationElement element, IntPtr handler);
        void AddStructureChangedEventHandler(IUIAutomationElement element, TreeScope scope, IUIAutomationCacheRequest cacheRequest, IntPtr handler);
        void RemoveStructureChangedEventHandler(IUIAutomationElement element, IntPtr handler);
        void AddFocusChangedEventHandler(IUIAutomationCacheRequest cacheRequest, IntPtr handler);
        void RemoveFocusChangedEventHandler(IntPtr handler);
        void RemoveAllEventHandlers();
        void IntNativeArrayToSafeArray(IntPtr array, int arrayCount, out Array safeArray);
        void IntSafeArrayToNativeArray(Array safeArray, out IntPtr array, out int arrayCount);
        void RectToVariant(tagRECT rc, out object var);
        void VariantToRect(object var, out tagRECT rc);
        void SafeArrayToRectNativeArray(Array rects, out IntPtr rectArray, out int rectArrayCount);
        void CreateProxyFactoryEntry(IntPtr factory, out IntPtr factoryEntry);
        void Get_ProxyFactoryMapping(out IntPtr mapping);
        void GetPropertyProgrammaticName(int property, [MarshalAs(UnmanagedType.BStr)] out string name);
        void GetPatternProgrammaticName(int pattern, [MarshalAs(UnmanagedType.BStr)] out string name);
        void PollForPotentialSupportedPatterns(IUIAutomationElement pElement, out Array patternIds, out Array patternNames);
        void PollForPotentialSupportedProperties(IUIAutomationElement pElement, out Array propertyIds, out Array propertyNames);
        void CheckNotSupported(object value, out int isNotSupported);
        void Get_ReservedNotSupportedValue(out object notSupportedValue);
        void Get_ReservedMixedAttributeValue(out object mixedAttributeValue);
        void ElementFromIAccessible(IntPtr pAccessible, int childId, out IUIAutomationElement element);
        void ElementFromIAccessibleBuildCache(IntPtr pAccessible, int childId, IUIAutomationCacheRequest cacheRequest, out IUIAutomationElement element);
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

    [ComImport]
    [Guid("a94cd8b1-0844-4cd6-9d2d-640537ab39e9")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IUIAutomationValuePattern
    {
        void SetValue([MarshalAs(UnmanagedType.BStr)] string val);
        void Get_CurrentValue([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CurrentIsReadOnly(out int retVal);
        void Get_CachedValue([MarshalAs(UnmanagedType.BStr)] out string retVal);
        void Get_CachedIsReadOnly(out int retVal);
    }

    [ComImport]
    [Guid("fb377fbe-8e4e-465c-9724-42ce025bfee6")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IUIAutomationInvokePattern
    {
        void Invoke();
    }

    public enum TreeScope
    {
        Element = 1,
        Children = 2,
        Descendants = 4,
        Subtree = 7,
        Ancestors = 8
    }

    public enum AutomationElementMode
    {
        None = 0,
        Full = 1
    }

    public enum PropertyConditionFlags
    {
        None = 0,
        IgnoreCase = 1
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct tagPOINT { public int x; public int y; }

    [StructLayout(LayoutKind.Sequential)]
    public struct tagRECT { public int left; public int top; public int right; public int bottom; }

    public class NativeRunner
    {
        public static void Run()
        {
            Console.WriteLine("NativeRunner: Initializing CUIAutomation...");
            var uia = (IUIAutomation)new CUIAutomationClass();
            Console.WriteLine("NativeRunner: CUIAutomation created successfully.");

            Process notepad = Process.Start("notepad.exe");
            System.Threading.Thread.Sleep(800);

            try
            {
                IUIAutomationElement rootElem;
                uia.ElementFromHandle(notepad.MainWindowHandle, out rootElem);
                string winName;
                rootElem.Get_CurrentName(out winName);
                Console.WriteLine("Window Name: " + winName);

                // Find Edit control
                IUIAutomationCondition trueCond;
                uia.CreateTrueCondition(out trueCond);
                IUIAutomationElementArray all;
                rootElem.FindAll(TreeScope.Descendants, trueCond, out all);
                int count;
                all.Get_Length(out count);
                Console.WriteLine("Descendants count: " + count);

                IUIAutomationElement editElem = null;
                for (int i = 0; i < count; i++)
                {
                    IUIAutomationElement el;
                    all.GetElement(i, out el);
                    string cls, name;
                    int ct;
                    el.Get_CurrentClassName(out cls);
                    el.Get_CurrentName(out name);
                    el.Get_CurrentControlType(out ct);
                    Console.WriteLine(string.Format("  [{0}] Class='{1}', Name='{2}', ControlType={3}", i, cls, name, ct));
                    if (cls == "Edit" && editElem == null)
                    {
                        editElem = el;
                    }
                }

                if (editElem != null)
                {
                    Console.WriteLine("\n--- Testing Native ValuePattern on Win32 Edit ---");
                    object valObj;
                    editElem.GetCurrentPattern(10002, out valObj); // UIA_ValuePatternId = 10002
                    if (valObj != null)
                    {
                        var valPattern = (IUIAutomationValuePattern)valObj;
                        string val;
                        valPattern.Get_CurrentValue(out val);
                        Console.WriteLine("Initial Value: '" + val + "'");

                        string testString = "機巧デスクトップ_Yayoi_Win32_NativeCOM_Success";
                        var sw = Stopwatch.StartNew();
                        valPattern.SetValue(testString);
                        sw.Stop();
                        Console.WriteLine(string.Format("SetValue executed in {0} ms", sw.ElapsedMilliseconds));

                        string afterVal;
                        valPattern.Get_CurrentValue(out afterVal);
                        Console.WriteLine("New Value: '" + afterVal + "'");

                        tagRECT rc;
                        editElem.Get_CurrentBoundingRectangle(out rc);
                        Console.WriteLine(string.Format("BoundingRect: ({0},{1},{2},{3})", rc.left, rc.top, rc.right, rc.bottom));
                        int cx = rc.left + (rc.right - rc.left) / 2;
                        int cy = rc.top + (rc.bottom - rc.top) / 2;
                        Console.WriteLine(string.Format("BoundingRect Center Point: ({0}, {1})", cx, cy));
                    }
                    else
                    {
                        Console.WriteLine("ValuePattern (10002) returned null!");
                    }
                }

                // Benchmark: CacheRequest Batching vs Per-Property Round-Trips
                Console.WriteLine("\n--- Benchmark: CacheRequest Batching vs Per-Property COM Round-Trips ---");
                int iterations = 100;
                var swUncached = Stopwatch.StartNew();
                for (int iter = 0; iter < iterations; iter++)
                {
                    for (int i = 0; i < count; i++)
                    {
                        IUIAutomationElement el;
                        all.GetElement(i, out el);
                        string cls, name, autoId;
                        int ct, enabled;
                        tagRECT rc;
                        el.Get_CurrentClassName(out cls);
                        el.Get_CurrentName(out name);
                        el.Get_CurrentAutomationId(out autoId);
                        el.Get_CurrentControlType(out ct);
                        el.Get_CurrentIsEnabled(out enabled);
                        el.Get_CurrentBoundingRectangle(out rc);
                    }
                }
                swUncached.Stop();
                long uncachedMs = swUncached.ElapsedMilliseconds;
                int totalProps = count * 6 * iterations;
                Console.WriteLine(string.Format("Uncached ({0} properties across {1} iterations): {2} ms ({3:F3} ms/property)",
                    totalProps, iterations, uncachedMs, (double)uncachedMs / totalProps));

                // CacheRequest batching
                IUIAutomationCacheRequest cacheReq;
                uia.CreateCacheRequest(out cacheReq);
                cacheReq.AddProperty(30012); // ClassName
                cacheReq.AddProperty(30005); // Name
                cacheReq.AddProperty(30011); // AutomationId
                cacheReq.AddProperty(30003); // ControlType
                cacheReq.AddProperty(30010); // IsEnabled
                cacheReq.AddProperty(30001); // BoundingRectangle
                cacheReq.Set_TreeScope(TreeScope.Subtree);

                var swCached = Stopwatch.StartNew();
                for (int iter = 0; iter < iterations; iter++)
                {
                    IUIAutomationElement cachedRoot;
                    rootElem.BuildUpdatedCache(cacheReq, out cachedRoot);
                    // Cached properties are already local in process memory
                    object vCls, vName, vAutoId, vCt, vEnabled, vRect;
                    cachedRoot.GetCachedPropertyValue(30012, out vCls);
                    cachedRoot.GetCachedPropertyValue(30005, out vName);
                    cachedRoot.GetCachedPropertyValue(30011, out vAutoId);
                    cachedRoot.GetCachedPropertyValue(30003, out vCt);
                    cachedRoot.GetCachedPropertyValue(30010, out vEnabled);
                    cachedRoot.GetCachedPropertyValue(30001, out vRect);
                }
                swCached.Stop();
                long cachedMs = swCached.ElapsedMilliseconds;
                Console.WriteLine(string.Format("Cached ({0} iterations of BuildUpdatedCache): {1} ms ({2:F3} ms/iteration)",
                    iterations, cachedMs, (double)cachedMs / iterations));

                if (cachedMs > 0)
                {
                    Console.WriteLine(string.Format("Batching Speedup: {0:F1}x faster", (double)uncachedMs / cachedMs));
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
[Karakuri.Probe.NativeRunner]::Run()
