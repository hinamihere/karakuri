// Karakuri — core/text (KARA-7: IME bypass)
//
// Text injection that never touches the keyboard.
//
// Why: the Japanese IME hooks the keyboard dispatch chain
// (WM_KEYDOWN -> TranslateMessage -> IMM/TSF). Anything typed as keystrokes opens a
// composition window, needs candidate confirmation, and drops characters when the app
// reads the buffer mid-composition. ValuePattern.SetValue runs inside the UIA provider
// and writes the UTF-16 string straight into the control's value buffer: zero keyboard
// messages, zero WM_IME_* messages, no composition dialog, no dropped characters.
//
// KARA-3 (research) verified this empirically against a Win32 Edit control:
// sub-millisecond write, exact read-back, zero IME events.

using System;
using System.Runtime.InteropServices;
using System.Windows.Automation;

namespace Karakuri.Text
{
    /// <summary>Result of a set_value operation, including the optional value read-back.</summary>
    public sealed class SetValueResult : TextActionResult
    {
        /// <summary>
        /// The control's value re-read after the write, or null when read-back was disabled or
        /// the element vanished immediately after the write. Comparing this against the requested
        /// text is how "no dropped characters" is asserted at runtime.
        /// </summary>
        public string ReadBackValue { get; internal set; }
    }

    /// <summary>
    /// Pushes text into a control through ValuePattern (contracts.md §4.2, action <c>set_value</c>).
    ///
    /// This module never synthesises input. It has no P/Invoke surface at all: no SendInput,
    /// no keybd_event, no SendKeys, no cursor moves. When a control exposes no ValuePattern the
    /// result is <c>error_category: pattern_missing</c> and nothing is written — the hardware
    /// fallback (click the bounding rectangle, wait for the in-place editor, then repeat) is the
    /// dispatcher's documented job, and only the dispatcher sets <c>fallback_attempted</c>.
    /// </summary>
    public static class TextInjector
    {
        /// <summary>Write <paramref name="text"/> and re-read the control's value afterwards.</summary>
        public static SetValueResult SetValue(AutomationElement element, string text)
        {
            return SetValue(element, text, true);
        }

        /// <param name="readBack">
        /// When true (default) the control's value is re-read after the write so the caller can
        /// detect a control that silently normalized or dropped characters. The read-back is
        /// verification only: if it fails after a successful write, the write is still reported
        /// as a success with <see cref="SetValueResult.ReadBackValue"/> left null.
        /// </param>
        public static SetValueResult SetValue(AutomationElement element, string text, bool readBack)
        {
            if (element == null)
                throw new ArgumentNullException("element", "set_value needs a resolved target (contracts.md §4.2).");
            if (text == null)
                throw new ArgumentNullException("text", "set_value requires a non-null value (contracts.md §4.2).");

            // contracts.md §8.3: re-validate the node immediately before acting. This reads one live
            // property, which is the only reliable liveness probe available — on a destroyed element
            // Name, ClassName and AutomationId throw ElementNotAvailableException, while IsEnabled and
            // ControlType silently fall back to defaults (verified against the Win32 UIA proxy) and
            // ValuePattern then reports IsReadOnly, which would misreport a stale handle as read-only.
            try
            {
                string liveName = element.Current.Name;
                if (liveName == null)
                    return Fail(TextActionResult.CategoryStaleHandle, null,
                        "The target element no longer reports a name.");
            }
            catch (ElementNotAvailableException ex)
            {
                return Fail(TextActionResult.CategoryStaleHandle, HResultOf(ex),
                    "The target element no longer exists (its window was destroyed) — re-validated just "
                  + "before the write as contracts.md §8.3 requires.");
            }

            object rawPattern = null;
            bool hasValuePattern;
            try
            {
                // GetCurrentPattern throws InvalidOperationException when a control has no provider for
                // the pattern; TryGetCurrentPattern reports it as false, which is the shape we want.
                hasValuePattern = element.TryGetCurrentPattern(ValuePattern.Pattern, out rawPattern);
            }
            catch (ElementNotAvailableException ex)
            {
                return Fail(TextActionResult.CategoryStaleHandle, HResultOf(ex),
                    "The target element was destroyed while its ValuePattern was being queried.");
            }
            catch (InvalidOperationException)
            {
                hasValuePattern = false;
            }

            ValuePattern valuePattern = hasValuePattern ? rawPattern as ValuePattern : null;
            if (valuePattern == null)
            {
                return Fail(TextActionResult.CategoryPatternMissing, null,
                    "The target exposes no ValuePattern (IValueProvider). Karakuri writes text only through the "
                  + "control's value buffer, so no input synthesis is attempted here; the dispatcher owns the "
                  + "documented BoundingRectangle fallback.");
            }

            bool isReadOnly;
            try
            {
                isReadOnly = valuePattern.Current.IsReadOnly;
            }
            catch (ElementNotAvailableException ex)
            {
                return Fail(TextActionResult.CategoryStaleHandle, HResultOf(ex),
                    "The target element disappeared while its ValuePattern was being queried.");
            }

            if (isReadOnly)
            {
                return Fail(TextActionResult.CategoryOsGeneric, null,
                    "The target exposes ValuePattern but reports IsReadOnly: the required writable value buffer "
                  + "is not available on this control.");
            }

            try
            {
                // The single write. UTF-16 string, provider-level buffer update, no keystrokes.
                valuePattern.SetValue(text);
            }
            catch (ElementNotAvailableException ex)
            {
                return Fail(TextActionResult.CategoryStaleHandle, HResultOf(ex),
                    "The target element was destroyed between resolution and the value write.");
            }
            catch (ElementNotEnabledException ex)
            {
                return Fail(TextActionResult.CategoryOsGeneric, HResultOf(ex),
                    "The target control is disabled, so its value provider refused the write.");
            }
            catch (COMException ex)
            {
                return Fail(TextActionResult.CategoryOsGeneric, HResultOf(ex),
                    "IValueProvider::SetValue failed with a COM error.");
            }
            catch (InvalidOperationException ex)
            {
                return Fail(TextActionResult.CategoryOsGeneric, HResultOf(ex),
                    "The value provider rejected the write: " + ex.Message);
            }

            SetValueResult result = new SetValueResult();
            result.SucceedAs("ValuePattern.SetValue accepted the text.");

            if (readBack)
            {
                try
                {
                    result.ReadBackValue = valuePattern.Current.Value;
                }
                catch (ElementNotAvailableException)
                {
                    result.Message += " Value read-back unavailable: the element disappeared right after the write.";
                }
                catch (COMException)
                {
                    result.Message += " Value read-back unavailable: the provider refused the read.";
                }
                catch (InvalidOperationException)
                {
                    result.Message += " Value read-back unavailable: the provider refused the read.";
                }
            }

            return result;
        }

        private static SetValueResult Fail(string errorCategory, uint? osErrorCode, string message)
        {
            SetValueResult result = new SetValueResult();
            result.FailAs(errorCategory, osErrorCode, message);
            return result;
        }

        /// <summary>
        /// HRESULT as unsigned decimal, so 0x80040201 (UIA_E_ELEMENTNOTAVAILABLE) reads as
        /// 2147746305 rather than -2147220991 — the same value the project docs write in hex.
        /// </summary>
        private static uint HResultOf(Exception ex)
        {
            return unchecked((uint)ex.HResult);
        }
    }
}
