// Karakuri — core/text (KARA-7: IME bypass and CP932 CSV boundary)
//
// The outcome type shared by every operation in this module. Its field names and
// value sets are taken verbatim from the frozen contract (contracts.md §2.1 and §2.2)
// so a dispatcher (KARA-8) or telemetry writer (KARA-11) can copy them into a
// telemetry.jsonl event without translation.

namespace Karakuri.Text
{
    /// <summary>
    /// Result of a text-module operation.
    ///
    /// On success: <c>Status == "success"</c>, <c>ErrorCategory == null</c>.
    /// On failure: <c>Status == "failure"</c> plus a non-null <c>ErrorCategory</c> drawn from
    /// the frozen <c>error_category</c> enum. This module never returns a failure without an
    /// <c>error_category</c> — "failure is data".
    ///
    /// <c>FallbackAttempted</c> is always <c>false</c> here: this module never falls back to
    /// input synthesis. The documented BoundingRectangle / SendInput fallback belongs to the
    /// dispatcher, which is the component that sets <c>fallback_attempted</c> on the event.
    /// </summary>
    public class TextActionResult
    {
        // contracts.md §2.1 — status enum
        public const string StatusSuccess = "success";
        public const string StatusFailure = "failure";
        public const string StatusFallbackApplied = "fallback_applied";
        public const string StatusUserAborted = "user_aborted";

        // contracts.md §2.2 — the subset of error_category this module can produce
        public const string CategoryPatternMissing = "pattern_missing";
        public const string CategoryStaleHandle = "stale_handle";
        public const string CategoryOsGeneric = "os_generic";

        /// <summary>True when the operation completed.</summary>
        public bool Success { get; internal set; }

        /// <summary>telemetry <c>status</c> field: "success" or "failure".</summary>
        public string Status { get; internal set; }

        /// <summary>telemetry <c>error_category</c>. Null when <see cref="Success"/>.</summary>
        public string ErrorCategory { get; internal set; }

        /// <summary>
        /// telemetry <c>os_error_code</c>: the 32-bit HRESULT of the failing COM/Win32 call,
        /// rendered as unsigned decimal (0x80040201 -> 2147746305) so the value matches the hex
        /// notation used throughout the project docs. Null when no OS call failed.
        /// </summary>
        public uint? OsErrorCode { get; internal set; }

        /// <summary>telemetry <c>fallback_attempted</c>. Always false for this module (see summary).</summary>
        public bool FallbackAttempted { get; internal set; }

        /// <summary>Human-readable diagnostic. Never contains a secret.</summary>
        public string Message { get; internal set; }

        internal void SucceedAs(string message)
        {
            Success = true;
            Status = StatusSuccess;
            ErrorCategory = null;
            OsErrorCode = null;
            FallbackAttempted = false;
            Message = message;
        }

        internal void FailAs(string errorCategory, uint? osErrorCode, string message)
        {
            Success = false;
            Status = StatusFailure;
            ErrorCategory = errorCategory;
            OsErrorCode = osErrorCode;
            FallbackAttempted = false;
            Message = message;
        }
    }
}
