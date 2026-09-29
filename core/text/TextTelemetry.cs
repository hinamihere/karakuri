// Karakuri — core/text (KARA-7)
//
// Telemetry formatting for failures raised by the text module.
//
// Boundary note: KARA-11 owns logs/telemetry.jsonl and KARA-8 decides when to append.
// This class only *formats* a contract-shaped event from a TextActionResult so that the
// fields the text module classifies can be appended by whoever owns the write. It does
// not decide file rotation, retention, or which failures get logged.

using System;
using System.Globalization;
using System.IO;
using System.Text;

namespace Karakuri.Text
{
    /// <summary>
    /// The per-execution half of a telemetry event (contracts.md §2.1): the fields every event
    /// carries regardless of which module raised the failure. Supplied by the caller because only
    /// the dispatcher / recipe engine knows them.
    /// </summary>
    public sealed class TelemetryEnvelope
    {
        private readonly string _executionMode;
        private readonly string _intent;
        private readonly string _windowTitle;
        private readonly string _treeSnapshotHash;
        private readonly string _llmOutputJson;
        private readonly string _resolvedTargetJson;

        /// <param name="executionMode">"mode_a" or "mode_b" (contracts.md §2.1).</param>
        /// <param name="intent">User intent. Truncated to 500 chars when the event is built.</param>
        /// <param name="windowTitle">Foreground window title. Truncated to 200 chars when built.</param>
        /// <param name="treeSnapshotHash">64-char SHA-256 hex; all zeros is rejected (§2.1).</param>
        /// <param name="llmOutputJson">Raw JSON of the parsed LLM response, or null (Mode A).</param>
        /// <param name="resolvedTargetJson">Raw JSON for resolved_target, or null when unresolved.</param>
        public TelemetryEnvelope(
            string executionMode,
            string intent,
            string windowTitle,
            string treeSnapshotHash,
            string llmOutputJson,
            string resolvedTargetJson)
        {
            if (executionMode != "mode_a" && executionMode != "mode_b")
                throw new ArgumentException("execution_mode must be 'mode_a' or 'mode_b' (contracts.md §2.1).", "executionMode");
            if (intent == null)
                throw new ArgumentNullException("intent");
            if (windowTitle == null)
                throw new ArgumentNullException("windowTitle");
            if (!IsRealSnapshotHash(treeSnapshotHash))
                throw new ArgumentException(
                    "tree_snapshot_hash must be 64 hex chars and must not be all zeros (contracts.md §2.1).",
                    "treeSnapshotHash");

            _executionMode = executionMode;
            _intent = intent;
            _windowTitle = windowTitle;
            _treeSnapshotHash = treeSnapshotHash;
            _llmOutputJson = llmOutputJson;
            _resolvedTargetJson = resolvedTargetJson;
        }

        public string ExecutionMode { get { return _executionMode; } }
        public string Intent { get { return _intent; } }
        public string WindowTitle { get { return _windowTitle; } }
        public string TreeSnapshotHash { get { return _treeSnapshotHash; } }
        public string LlmOutputJson { get { return _llmOutputJson; } }
        public string ResolvedTargetJson { get { return _resolvedTargetJson; } }

        public static bool IsRealSnapshotHash(string hash)
        {
            if (hash == null || hash.Length != 64)
                return false;
            bool anyNonZero = false;
            for (int i = 0; i < hash.Length; i++)
            {
                char c = hash[i];
                bool hex = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
                if (!hex)
                    return false;
                if (c != '0')
                    anyNonZero = true;
            }
            return anyNonZero;
        }
    }

    /// <summary>Builds schema-conformant telemetry JSONL events; appends them when asked to.</summary>
    public static class TextTelemetry
    {
        /// <summary>Contracts.md §2.1 truncation limits.</summary>
        public const int MaxIntentChars = 500;
        public const int MaxWindowTitleChars = 200;

        /// <summary>
        /// Builds one telemetry.jsonl line for a failure produced by this module.
        /// Field order and names match contracts.md §2.1 exactly.
        /// </summary>
        /// <param name="timestampIso8601Utc">
        /// ISO 8601 UTC timestamp; pass null to use the current wall clock. Tests pass an explicit
        /// value so their output is byte-stable.
        /// </param>
        public static string BuildFailureLine(
            TelemetryEnvelope envelope,
            TextActionResult result,
            string timestampIso8601Utc)
        {
            if (envelope == null)
                throw new ArgumentNullException("envelope");
            if (result == null)
                throw new ArgumentNullException("result");
            if (result.Success)
                throw new ArgumentException("BuildFailureLine is for failures; a success event is not this module's call.", "result");
            if (result.ErrorCategory == null)
                throw new ArgumentException("A failure must carry an error_category (contracts.md §2.2).", "result");

            string timestamp = timestampIso8601Utc ?? UtcNowIso8601();

            StringBuilder sb = new StringBuilder(256);
            sb.Append('{');
            AppendString(sb, "timestamp", timestamp);
            sb.Append(',');
            AppendString(sb, "execution_mode", envelope.ExecutionMode);
            sb.Append(',');
            AppendString(sb, "intent", Truncate(envelope.Intent, MaxIntentChars));
            sb.Append(',');
            AppendString(sb, "window_title", Truncate(envelope.WindowTitle, MaxWindowTitleChars));
            sb.Append(',');
            AppendString(sb, "tree_snapshot_hash", envelope.TreeSnapshotHash);
            sb.Append(',');
            sb.Append("\"llm_output\":").Append(envelope.LlmOutputJson ?? "null");
            sb.Append(',');
            sb.Append("\"resolved_target\":").Append(envelope.ResolvedTargetJson ?? "null");
            sb.Append(',');
            AppendString(sb, "status", result.Status);
            sb.Append(',');
            AppendString(sb, "error_category", result.ErrorCategory);
            sb.Append(',');
            sb.Append("\"os_error_code\":");
            if (result.OsErrorCode.HasValue)
                sb.Append(result.OsErrorCode.Value.ToString(CultureInfo.InvariantCulture));
            else
                sb.Append("null");
            sb.Append(',');
            sb.Append("\"fallback_attempted\":").Append(result.FallbackAttempted ? "true" : "false");
            sb.Append('}');
            return sb.ToString();
        }

        /// <summary>Convenience overload that stamps the event with the current wall clock.</summary>
        public static string BuildFailureLine(TelemetryEnvelope envelope, TextActionResult result)
        {
            return BuildFailureLine(envelope, result, null);
        }

        /// <summary>
        /// Appends one line to an append-only JSONL log (creates the file if needed).
        /// Never rewrites existing content — telemetry.jsonl is append-only per contracts.md §2.
        /// </summary>
        public static void AppendLine(string path, string jsonLine)
        {
            if (path == null)
                throw new ArgumentNullException("path");
            if (jsonLine == null)
                throw new ArgumentNullException("jsonLine");

            string directory = Path.GetDirectoryName(Path.GetFullPath(path));
            if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
                Directory.CreateDirectory(directory);

            using (FileStream stream = new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.Read))
            using (StreamWriter writer = new StreamWriter(stream, new UTF8Encoding(false)))
            {
                writer.WriteLine(jsonLine);
            }
        }

        public static string UtcNowIso8601()
        {
            return DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture);
        }

        private static string Truncate(string value, int maxChars)
        {
            if (value == null)
                return string.Empty;
            return value.Length <= maxChars ? value : value.Substring(0, maxChars);
        }

        private static void AppendString(StringBuilder sb, string key, string value)
        {
            sb.Append('"').Append(Escape(key)).Append("\":\"").Append(Escape(value ?? string.Empty)).Append('"');
        }

        /// <summary>JSON string escaping. Non-ASCII is written through as UTF-8, not \u-escaped.</summary>
        private static string Escape(string value)
        {
            StringBuilder sb = new StringBuilder(value.Length + 8);
            for (int i = 0; i < value.Length; i++)
            {
                char c = value[i];
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20)
                            sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        else
                            sb.Append(c);
                        break;
                }
            }
            return sb.ToString();
        }
    }
}
