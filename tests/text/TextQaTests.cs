// Karakuri — tests/text (KARA-7)
//
// QA proof for the text handling module. Run with build/run-text-tests.cmd (no network, no
// third-party packages; it compiles with the in-box .NET Framework compiler).
//
// The acceptance criterion this file exists for:
//   "a Japanese date field accepts 2026/08/01 with no IME composition dialog and no dropped
//    characters, proven by a QA test"
// is case ime_bypass_japanese_date_field. It is proven by counting the window messages the
// target control actually receives — zero keyboard messages and zero IME composition messages —
// plus an exact value read-back, rather than by looking at a screenshot.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Automation;
using Karakuri.Text;

namespace Karakuri.Tests.Text
{
    internal static class TextQaTests
    {
        private const string AcceptanceDate = "2026/08/01";
        private const string DateFieldName = "納品日";
        private const string MemoFieldName = "摘要";
        private const string ReadOnlyFieldName = "出力先";
        private const string PaneName = "検索条件";

        private static readonly List<string> Output = new List<string>();
        private static readonly List<string> Failures = new List<string>();
        private static readonly List<string> Notes = new List<string>();
        private static int _caseCount;
        private static int _failedCases;
        private static string _repoRoot;
        private static string _lastTreeDump = string.Empty;

        private static int Main(string[] args)
        {
            try
            {
                Console.OutputEncoding = new UTF8Encoding(false);
            }
            catch (IOException)
            {
                // no console attached; the results file still gets written
            }

            _repoRoot = args.Length > 0 ? args[0] : FindRepoRoot();
            if (_repoRoot == null || !Directory.Exists(Path.Combine(_repoRoot, "core", "text")))
            {
                Console.Error.WriteLine("Could not locate the repository root (core/text not found).");
                return 2;
            }

            Emit("Karakuri KARA-7 — text module QA");
            Emit("repo    : " + _repoRoot);
            Emit("runtime : " + Environment.Version + " / " + Environment.OSVersion);
            Emit("");

            Case("ime_bypass_japanese_date_field",
                 "日本語日付フィールドが IME 構成を起こさず 2026/08/01 を受入する / Japanese date field accepts 2026/08/01 with no IME composition",
                 TestJapaneseDateField);

            Case("ime_bypass_japanese_text_no_dropped_chars",
                 "日本語テキストが欠落なく書き込まれる / Japanese text written with no dropped characters",
                 TestJapaneseTextIntegrity);

            Case("failure_missing_value_pattern",
                 "ValuePattern なしのターゲットは pattern_missing で失敗する / target without ValuePattern fails with pattern_missing",
                 TestMissingValuePattern);

            Case("failure_readonly_control",
                 "読み取り専用コントロールは os_generic で失敗する / read-only control fails with os_generic",
                 TestReadOnlyControl);

            Case("failure_stale_handle",
                 "破棄済みウィンドウは stale_handle で失敗する / destroyed window fails with stale_handle",
                 TestStaleHandle);

            Case("telemetry_failure_event_schema",
                 "失敗は telemetry.jsonl に契約どおりのイベントで出力される / failures land in telemetry.jsonl with the contracted schema",
                 TestTelemetryEvent);

            Case("csv_cp932_roundtrip",
                 "CP932 CSV の読み書きが往復する / CP932 CSV round-trips byte-exactly",
                 TestCsvCp932RoundTrip);

            Case("csv_cp932_known_fixture",
                 "既知の CP932 バイト列を正しく復号する / known CP932 byte fixture decodes correctly",
                 TestCsvCp932Fixture);

            Case("csv_utf8_auto_detect",
                 "BOM なし/あり UTF-8 CSV を自動判別する / UTF-8 CSV detected with and without BOM",
                 TestCsvUtf8AutoDetect);

            Case("csv_strict_read_reports_bad_byte",
                 "不正バイトは置換せず位置を報告する / undecodable byte fails with its offset instead of being replaced",
                 TestCsvStrictRead);

            Case("csv_strict_write_refuses_unmappable",
                 "CP932 に符号化できない文字は書き込まない / unencodable character refuses to write and locates the cell",
                 TestCsvStrictWrite);

            Case("static_encoding_only_at_csv_boundary",
                 "CP932 変換は CSV 境界の CsvBoundary.cs のみ / CP932 conversion lives only in CsvBoundary.cs",
                 TestEncodingConfinement);

            Case("static_no_input_synthesis_in_text_module",
                 "core/text に入力合成 API はない / core/text contains no input-synthesis API",
                 TestNoInputSynthesis);

            Emit("");
            Emit("TOTAL: " + _caseCount + "  PASS: " + (_caseCount - _failedCases) + "  FAIL: " + _failedCases);
            Emit(_failedCases == 0 ? "RESULT: PASS" : "RESULT: FAIL");

            string resultsPath = Path.Combine(_repoRoot, "tests", "text", "test-results.txt");
            File.WriteAllText(resultsPath, string.Join(Environment.NewLine, Output.ToArray()) + Environment.NewLine,
                new UTF8Encoding(false));

            return _failedCases == 0 ? 0 : 1;
        }

        // ================================================================ cases

        private static void TestJapaneseDateField()
        {
            using (TargetWindowHost host = new TargetWindowHost())
            {
                host.Start();
                AutomationElement root = AutomationElement.FromHandle(host.WindowHandle);
                AutomationElement dateField = FindByControlType(root, "ControlType.Edit", DateFieldName);
                Check(dateField != null, "the Japanese date field must be present in the a11y tree" + TreeDump());
                if (dateField == null)
                    return;

                MessageCounters before = host.Form.Counters.Copy();
                SetValueResult result = TextInjector.SetValue(dateField, AcceptanceDate);
                Thread.Sleep(50);
                MessageCounters after = host.Form.Counters.Copy();

                Check(result.Success, "SetValue must succeed — status=" + result.Status
                    + " category=" + result.ErrorCategory + " message=" + result.Message);
                CheckEqual(AcceptanceDate, result.ReadBackValue, "read-back of the date field");

                Check(after.CompositionTotal - before.CompositionTotal == 0,
                    "no WM_IME_*COMPOSITION message may arrive (that is the IME composition dialog) — delta="
                    + (after.CompositionTotal - before.CompositionTotal));
                Check(after.KeyboardTotal - before.KeyboardTotal == 0,
                    "no WM_KEYDOWN / WM_CHAR may arrive (that would be keystroke typing) — delta="
                    + (after.KeyboardTotal - before.KeyboardTotal));
                Check(after.BufferWriteTotal - before.BufferWriteTotal >= 1,
                    "the value must land in the control buffer via WM_SETTEXT / EM_REPLACESEL");

                AutomationElement reFound = FindByControlType(
                    AutomationElement.FromHandle(host.WindowHandle), "ControlType.Edit", DateFieldName);
                string independent = ReadValue(reFound);
                CheckEqual(AcceptanceDate, independent, "independent re-read through a fresh UIA element");

                Note("counters before: " + before.Describe());
                Note("counters after : " + after.Describe());
            }
        }

        private static void TestJapaneseTextIntegrity()
        {
            using (TargetWindowHost host = new TargetWindowHost())
            {
                host.Start();
                AutomationElement root = AutomationElement.FromHandle(host.WindowHandle);
                AutomationElement memoField = FindByControlType(root, "ControlType.Edit", MemoFieldName);
                Check(memoField != null, "the memo field must be present in the a11y tree" + TreeDump());
                if (memoField == null)
                    return;

                // Every character here is one a keystroke/IME path tends to mangle: the copyright
                // circle, full-width punctuation, the yen sign and a comma inside a number.
                string value = "弥生会計・仕訳㈱ 2026/08/01 ￥150,000（税込）〜";

                MessageCounters before = host.Form.Counters.Copy();
                SetValueResult result = TextInjector.SetValue(memoField, value);
                Thread.Sleep(50);
                MessageCounters after = host.Form.Counters.Copy();

                Check(result.Success, "SetValue must succeed — " + result.Message);
                CheckEqual(value, result.ReadBackValue, "read-back must be byte-identical to the requested text");
                Check(result.ReadBackValue == null || result.ReadBackValue.Length == value.Length,
                    "read-back length must match (no characters dropped)");
                Check(after.CompositionTotal - before.CompositionTotal == 0,
                    "no IME composition messages — delta=" + (after.CompositionTotal - before.CompositionTotal));
                Check(after.KeyboardTotal - before.KeyboardTotal == 0,
                    "no keyboard messages — delta=" + (after.KeyboardTotal - before.KeyboardTotal));

                Note("counters after: " + after.Describe());
            }
        }

        private static void TestMissingValuePattern()
        {
            using (TargetWindowHost host = new TargetWindowHost())
            {
                host.Start();
                AutomationElement root = AutomationElement.FromHandle(host.WindowHandle);
                AutomationElement pane = FindByControlType(root, "ControlType.Pane", PaneName);
                Check(pane != null, "the pattern-less panel must be present in the a11y tree" + TreeDump());
                if (pane == null)
                    return;

                SetValueResult result = TextInjector.SetValue(pane, "値");
                Check(!result.Success, "setting a value on a control with no ValuePattern must fail");
                CheckEqual(TextActionResult.StatusFailure, result.Status, "status");
                CheckEqual(TextActionResult.CategoryPatternMissing, result.ErrorCategory, "error_category");
                Check(result.OsErrorCode == null, "os_error_code must be null (no OS call failed)");
                Check(!result.FallbackAttempted,
                    "fallback_attempted must be false — this module never falls back to input synthesis");
                Note("message: " + result.Message);
            }
        }

        private static void TestReadOnlyControl()
        {
            using (TargetWindowHost host = new TargetWindowHost())
            {
                host.Start();
                AutomationElement root = AutomationElement.FromHandle(host.WindowHandle);
                AutomationElement readOnly = FindByControlType(root, "ControlType.Edit", ReadOnlyFieldName);
                Check(readOnly != null, "the read-only field must be present in the a11y tree" + TreeDump());
                if (readOnly == null)
                    return;

                SetValueResult result = TextInjector.SetValue(readOnly, "書き換え");
                Check(!result.Success, "writing to a read-only control must fail");
                CheckEqual(TextActionResult.StatusFailure, result.Status, "status");
                CheckEqual(TextActionResult.CategoryOsGeneric, result.ErrorCategory,
                    "error_category — the pattern exists but refuses, so this is not pattern_missing");
                Check(!result.FallbackAttempted, "fallback_attempted");
                Note("message: " + result.Message);
            }
        }

        private static void TestStaleHandle()
        {
            using (TargetWindowHost host = new TargetWindowHost())
            {
                host.Start();
                AutomationElement root = AutomationElement.FromHandle(host.WindowHandle);
                AutomationElement dateField = FindByControlType(root, "ControlType.Edit", DateFieldName);
                Check(dateField != null, "the date field must be present in the a11y tree" + TreeDump());
                if (dateField == null)
                    return;

                host.CloseWindow();

                bool becameStale = SpinUntil(delegate
                {
                    try
                    {
                        string ignored = dateField.Current.Name;
                        return false;
                    }
                    catch (ElementNotAvailableException)
                    {
                        return true;
                    }
                    catch (Exception)
                    {
                        return false;
                    }
                }, 10000);

                Check(becameStale, "destroying the window must invalidate the element within 10 s");
                if (!becameStale)
                    return;

                SetValueResult result = TextInjector.SetValue(dateField, AcceptanceDate);
                Check(!result.Success, "SetValue on a destroyed element must fail");
                CheckEqual(TextActionResult.CategoryStaleHandle, result.ErrorCategory, "error_category");
                CheckEqual(TextActionResult.StatusFailure, result.Status, "status");
                Check(result.OsErrorCode.HasValue, "os_error_code must carry the failing HRESULT");
                Note("os_error_code=" + (result.OsErrorCode.HasValue
                    ? result.OsErrorCode.Value + " (0x" + result.OsErrorCode.Value.ToString("X8") + ")"
                    : "null") + " — " + result.Message);
            }
        }

        private static void TestTelemetryEvent()
        {
            // Two real failures produced by this module, formatted and appended the way the
            // dispatcher will do it once KARA-11's writer is wired in.
            string hash = Sha256Hex("kara-7 telemetry conformance");
            string intent = "テスト: KARA-7 IMEバイパス検証";
            string windowTitle = "弥生会計 2026 - 仕訳入力";

            TelemetryEnvelope envelope =
                new TelemetryEnvelope("mode_a", intent, windowTitle, hash, null, null);

            using (TargetWindowHost host = new TargetWindowHost())
            {
                host.Start();
                AutomationElement root = AutomationElement.FromHandle(host.WindowHandle);

                AutomationElement pane = FindByControlType(root, "ControlType.Pane", PaneName);
                AutomationElement readOnly = FindByControlType(root, "ControlType.Edit", ReadOnlyFieldName);
                Check(pane != null && readOnly != null, "fixture fields must be present" + TreeDump());
                if (pane == null || readOnly == null)
                    return;

                SetValueResult missing = TextInjector.SetValue(pane, "値");
                SetValueResult readOnlyResult = TextInjector.SetValue(readOnly, "書き換え");

                // Wall-clock timestamps: these two lines are appended to the real log below, so
                // they must be honest about when the run happened.
                string line = TextTelemetry.BuildFailureLine(envelope, missing);
                Dictionary<string, object> parsed = ParseJson(line);
                Check(parsed != null, "the event must be valid JSON — got: " + line);
                if (parsed == null)
                    return;

                CheckContractFields(parsed, "mode_a");
                CheckEqual("failure", GetString(parsed, "status"), "status");
                CheckEqual(TextActionResult.CategoryPatternMissing, GetString(parsed, "error_category"), "error_category");
                Check(!parsed.ContainsKey("os_error_code") || parsed["os_error_code"] == null,
                    "os_error_code must be null for a missing pattern");
                CheckEqual(false, parsed["fallback_attempted"], "fallback_attempted");
                Check(parsed["llm_output"] == null, "llm_output must be null outside a Mode B plan");
                Check(parsed["resolved_target"] == null, "resolved_target is unknown to this module");

                // Contracts.md §2.1 truncation limits.
                string longIntent = new string('あ', 600);
                TelemetryEnvelope longEnvelope =
                    new TelemetryEnvelope("mode_b", longIntent, windowTitle, hash, null, null);
                string line2 = TextTelemetry.BuildFailureLine(longEnvelope, readOnlyResult);
                Dictionary<string, object> parsed2 = ParseJson(line2);
                Check(parsed2 != null, "the second event must be valid JSON — got: " + line2);
                if (parsed2 == null)
                    return;

                CheckContractFields(parsed2, "mode_b");
                CheckEqual(TextActionResult.CategoryOsGeneric, GetString(parsed2, "error_category"), "error_category");
                string truncated = GetString(parsed2, "intent");
                Check(truncated.Length == 500, "intent must be truncated to 500 chars, was " + truncated.Length);
                CheckEqual("failure", GetString(parsed2, "status"), "status");

                // The timestamp override exists so a test or a backfill can pin one; prove it.
                string pinned = TextTelemetry.BuildFailureLine(envelope, missing, "2026-09-29T00:00:00.000Z");
                Dictionary<string, object> parsedPinned = ParseJson(pinned);
                Check(parsedPinned != null
                      && string.Equals(GetString(parsedPinned, "timestamp"), "2026-09-29T00:00:00.000Z",
                                       StringComparison.Ordinal),
                    "an explicit timestamp must be honoured verbatim — got: " + pinned);

                // Envelope validation: an all-zero hash is forbidden by contracts.md §2.1.
                bool rejected = false;
                try
                {
                    new TelemetryEnvelope("mode_a", intent, windowTitle, new string('0', 64), null, null);
                }
                catch (ArgumentException)
                {
                    rejected = true;
                }
                Check(rejected, "an all-zero tree_snapshot_hash must be rejected (contracts.md §2.1)");

                // Append both to the contracted path and read them back.
                string logPath = Path.Combine(_repoRoot, "logs", "telemetry.jsonl");
                int before = File.Exists(logPath) ? File.ReadAllLines(logPath).Length : 0;
                TextTelemetry.AppendLine(logPath, line);
                TextTelemetry.AppendLine(logPath, line2);
                string[] afterLines = File.ReadAllLines(logPath);
                Check(afterLines.Length - before == 2,
                    "exactly two lines must be appended — got " + (afterLines.Length - before));
                Check(ParseJson(afterLines[afterLines.Length - 1]) != null,
                    "the appended line must parse back from logs/telemetry.jsonl");
                Note("appended to " + logPath);
                Note("event: " + line);
            }
        }

        private static void TestCsvCp932RoundTrip()
        {
            string[][] rows = new string[][]
            {
                new string[] { "日付", "摘要", "金額" },
                new string[] { "2026/08/01", "振込入金", "150000" },
                new string[] { "㈱鉄鋼", "特売（日本語）", "0" }
            };

            CsvWriteResult encoded = CsvBoundary.EncodeRows(rows, CsvEncoding.Cp932);
            Check(encoded.Success, "encoding must succeed — " + encoded.Message);
            Check(encoded.Data != null, "encoded bytes must be produced");
            if (!encoded.Success || encoded.Data == null)
                return;

            CheckEqual(3, encoded.RowsWritten, "RowsWritten");

            // The bytes must be CP932, and must NOT be valid UTF-8 — otherwise the auto detector
            // would route them the wrong way.
            string decodedAsCp932 = CsvBoundary.Cp932.GetString(encoded.Data);
            Check(decodedAsCp932.Contains("日付"), "the bytes must decode back to the original header");
            Check(decodedAsCp932.Contains("㈱鉄鋼"), "the bytes must decode back to the original Japanese cell");
            bool validUtf8 = true;
            try
            {
                new UTF8Encoding(false, true).GetString(encoded.Data);
            }
            catch (DecoderFallbackException)
            {
                validUtf8 = false;
            }
            Check(!validUtf8, "CP932 output must not be valid UTF-8");

            string directory = Path.Combine(_repoRoot, "tests", "text", "tmp");
            string path = Path.Combine(directory, "roundtrip-cp932.csv");
            CsvWriteResult written = CsvBoundary.Write(path, rows, CsvEncoding.Cp932);
            Check(written.Success, "writing the CSV must succeed — " + written.Message);
            if (!written.Success)
                return;
            Check(File.Exists(path), "the CSV file must exist after a successful write");

            CsvReadResult readBack = CsvBoundary.Read(path);
            Check(readBack.Success, "reading the CSV back must succeed — " + readBack.Message);
            if (!readBack.Success)
                return;
            Check(readBack.ResolvedEncoding.HasValue && readBack.ResolvedEncoding.Value == CsvEncoding.Cp932,
                "auto detection must resolve the file to CP932, got " + readBack.ResolvedEncoding);
            CheckEqual(rows.Length, readBack.Rows.Length, "row count after round-trip");
            for (int r = 0; r < rows.Length && r < readBack.Rows.Length; r++)
            {
                CheckEqual(rows[r].Length, readBack.Rows[r].Length, "column count of row " + r);
                for (int c = 0; c < rows[r].Length && c < readBack.Rows[r].Length; c++)
                    CheckEqual(rows[r][c], readBack.Rows[r][c], "cell [" + r + "][" + c + "]");
            }

            // File bytes must survive the round-trip unchanged.
            byte[] onDisk = File.ReadAllBytes(path);
            Check(onDisk.Length == encoded.Data.Length && BytesEqual(onDisk, encoded.Data),
                "file bytes must match the in-memory encoding exactly");
            Note("wrote " + onDisk.Length + " bytes of CP932 to " + path);
        }

        private static void TestCsvCp932Fixture()
        {
            // "日付,摘要,金額\r\n2026/08/01,振込入金,150000\r\n㈱鉄鋼,特売（日本語）,0\r\n" encoded as CP932,
            // captured from an independent encoder so this test does not just agree with itself.
            byte[] fixture = new byte[]
            {
                0x93, 0xFA, 0x95, 0x74, 0x2C, 0x93, 0x45, 0x97, 0x76, 0x2C, 0x8B, 0xE0, 0x8A, 0x7A, 0x0D, 0x0A,
                0x32, 0x30, 0x32, 0x36, 0x2F, 0x30, 0x38, 0x2F, 0x30, 0x31, 0x2C, 0x90, 0x55, 0x8D, 0x9E, 0x93,
                0xFC, 0x8B, 0xE0, 0x2C, 0x31, 0x35, 0x30, 0x30, 0x30, 0x30, 0x0D, 0x0A, 0x87, 0x8A, 0x93, 0x53,
                0x8D, 0x7C, 0x2C, 0x93, 0xC1, 0x94, 0x84, 0x81, 0x69, 0x93, 0xFA, 0x96, 0x7B, 0x8C, 0xEA, 0x81,
                0x6A, 0x2C, 0x30, 0x0D, 0x0A
            };

            CsvReadResult read = CsvBoundary.DecodeRows(fixture, CsvEncoding.Auto);
            Check(read.Success, "the CP932 fixture must decode — " + read.Message);
            if (!read.Success)
                return;

            Check(read.ResolvedEncoding.HasValue && read.ResolvedEncoding.Value == CsvEncoding.Cp932,
                "auto detection must resolve the fixture to CP932");
            CheckEqual(3, read.Rows.Length, "row count");
            CheckEqual("日付", read.Rows[0][0], "cell [0][0]");
            CheckEqual("振込入金", read.Rows[1][1], "cell [1][1]");
            CheckEqual("㈱鉄鋼", read.Rows[2][0], "cell [2][0]");
            CheckEqual("特売（日本語）", read.Rows[2][1], "cell [2][1]");
        }

        private static void TestCsvUtf8AutoDetect()
        {
            string[][] rows = new string[][]
            {
                new string[] { "日付", "摘要" },
                new string[] { "2026/08/01", "テスト" }
            };
            string body = "日付,摘要\r\n2026/08/01,テスト\r\n";

            byte[] withoutBom = new UTF8Encoding(false).GetBytes(body);
            CsvReadResult plain = CsvBoundary.DecodeRows(withoutBom, CsvEncoding.Auto);
            Check(plain.Success, "BOM-less UTF-8 must decode — " + plain.Message);
            Check(plain.ResolvedEncoding.HasValue && plain.ResolvedEncoding.Value == CsvEncoding.Utf8,
                "BOM-less UTF-8 must be detected as UTF-8");
            if (plain.Success)
            {
                CheckEqual("日付", plain.Rows[0][0], "cell [0][0]");
                CheckEqual("テスト", plain.Rows[1][1], "cell [1][1]");
            }

            byte[] withBom = new byte[withoutBom.Length + 3];
            withBom[0] = 0xEF; withBom[1] = 0xBB; withBom[2] = 0xBF;
            Buffer.BlockCopy(withoutBom, 0, withBom, 3, withoutBom.Length);
            CsvReadResult bom = CsvBoundary.DecodeRows(withBom, CsvEncoding.Auto);
            Check(bom.Success, "UTF-8 BOM must decode — " + bom.Message);
            Check(bom.ResolvedEncoding.HasValue && bom.ResolvedEncoding.Value == CsvEncoding.Utf8,
                "UTF-8 BOM must be detected as UTF-8");
            if (bom.Success)
                CheckEqual("日付", bom.Rows[0][0], "BOM must be stripped, cell [0][0]");

            // UTF-16 is out of contract scope and must be rejected with a clear message, not guessed at.
            byte[] utf16 = new byte[] { 0xFF, 0xFE, 0x41, 0x00, 0x42, 0x00 };
            CsvReadResult rejected = CsvBoundary.DecodeRows(utf16, CsvEncoding.Auto);
            Check(!rejected.Success, "a UTF-16 CSV must be rejected, not silently mis-decoded");
            CheckEqual(TextActionResult.CategoryOsGeneric, rejected.ErrorCategory, "error_category");
            Note("UTF-16 rejection message: " + rejected.Message);
        }

        private static void TestCsvStrictRead()
        {
            // "日" (0x93 0xFA) then a lead byte 0x93 followed by trail byte 0x20, which is outside
            // the legal trail range 0x40-0x7E / 0x80-0xFC. The bytes 0x80/0xA0/0xFD-0xFF are NOT
            // invalid to .NET — Windows CP932 defines them in the private-use area — so a genuine
            // broken sequence is what proves strict decoding.
            byte[] bad = new byte[] { 0x93, 0xFA, 0x93, 0x20, 0x2C };
            CsvReadResult read = CsvBoundary.DecodeRows(bad, CsvEncoding.Cp932);
            Check(!read.Success, "an undecodable byte must fail the read");
            CheckEqual(TextActionResult.CategoryOsGeneric, read.ErrorCategory, "error_category");
            Check(read.Rows == null, "no rows may be returned when decoding failed");
            Check(read.Message != null && read.Message.Contains("offset"),
                "the failure must report the byte offset — got: " + read.Message);
            Note("message: " + read.Message);
        }

        private static void TestCsvStrictWrite()
        {
            string[][] rows = new string[][]
            {
                new string[] { "日付", "メモ" },
                new string[] { "2026/08/01", "🎮" }
            };

            CsvWriteResult encoded = CsvBoundary.EncodeRows(rows, CsvEncoding.Cp932);
            Check(!encoded.Success, "a character with no CP932 representation must fail the write");
            CheckEqual(TextActionResult.CategoryOsGeneric, encoded.ErrorCategory, "error_category");
            Check(encoded.Data == null, "no bytes may be produced when encoding failed");
            CheckEqual(1, encoded.RowIndex, "row of the offending cell");
            CheckEqual(1, encoded.ColumnIndex, "column of the offending cell");
            CheckEqual("\U0001F3AE", encoded.OffendingText,
                "the offending character must be reported as it appears in the cell");
            Note("message: " + encoded.Message);

            // Nothing may reach disk.
            string path = Path.Combine(_repoRoot, "tests", "text", "tmp", "must-not-exist.csv");
            if (File.Exists(path))
                File.Delete(path);
            CsvWriteResult written = CsvBoundary.Write(path, rows, CsvEncoding.Cp932);
            Check(!written.Success, "the file write must fail too");
            Check(!File.Exists(path), "no partial file may be left behind");
        }

        private static void TestEncodingConfinement()
        {
            string textDirectory = Path.Combine(_repoRoot, "core", "text");
            string[] files = Directory.GetFiles(textDirectory, "*.cs");
            Check(files.Length > 0, "core/text must contain source files");

            List<string> offenders = new List<string>();
            foreach (string file in files)
            {
                string name = Path.GetFileName(file);
                if (string.Equals(name, "CsvBoundary.cs", StringComparison.OrdinalIgnoreCase))
                    continue;
                string content = File.ReadAllText(file);
                if (content.Contains("GetEncoding("))
                    offenders.Add(name);
            }

            Check(offenders.Count == 0,
                "Encoding.GetEncoding must only be called from CsvBoundary.cs — found in: "
                + string.Join(", ", offenders.ToArray()));
            Note("scanned " + files.Length + " file(s) in core/text");
        }

        private static void TestNoInputSynthesis()
        {
            string textDirectory = Path.Combine(_repoRoot, "core", "text");
            string[] files = Directory.GetFiles(textDirectory, "*.cs");

            // Call-shaped tokens: an input-synthesis API invoked anywhere in core/text is a bug,
            // because text must reach a control only through its value buffer.
            string[] forbidden =
            {
                "SendInput(", "keybd_event(", "SendKeys.", "SetCursorPos(", "mouse_event(",
                "PostMessage(", "SendMessage(", "MapVirtualKey(", "LoadKeyboardLayout(",
                "[DllImport"
            };

            List<string> offenders = new List<string>();
            foreach (string file in files)
            {
                string content = File.ReadAllText(file);
                foreach (string token in forbidden)
                {
                    if (content.Contains(token))
                        offenders.Add(Path.GetFileName(file) + " -> " + token);
                }
            }

            Check(offenders.Count == 0,
                "core/text must not synthesise input — found: " + string.Join("; ", offenders.ToArray()));
            Note("scanned " + files.Length + " file(s) in core/text for " + forbidden.Length + " forbidden APIs");
        }

        // ================================================================ helpers

        private static void CheckContractFields(Dictionary<string, object> parsed, string expectedMode)
        {
            string[] required =
            {
                "timestamp", "execution_mode", "intent", "window_title", "tree_snapshot_hash",
                "llm_output", "resolved_target", "status", "error_category", "os_error_code",
                "fallback_attempted"
            };
            foreach (string key in required)
                Check(parsed.ContainsKey(key), "telemetry event must carry the field '" + key + "'");

            if (!parsed.ContainsKey("timestamp"))
                return;

            string timestamp = GetString(parsed, "timestamp");
            Check(System.Text.RegularExpressions.Regex.IsMatch(
                    timestamp, @"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"),
                "timestamp must be ISO 8601 UTC with milliseconds — got '" + timestamp + "'");
            CheckEqual(expectedMode, GetString(parsed, "execution_mode"), "execution_mode");

            string hash = GetString(parsed, "tree_snapshot_hash");
            Check(TelemetryEnvelope.IsRealSnapshotHash(hash),
                "tree_snapshot_hash must be 64 non-zero hex chars — got '" + hash + "'");

            string windowTitle = GetString(parsed, "window_title");
            Check(windowTitle.Length <= 200, "window_title must be at most 200 chars, was " + windowTitle.Length);
            Check(GetString(parsed, "intent").Length <= 500,
                "intent must be at most 500 chars, was " + GetString(parsed, "intent").Length);
            Check(parsed["status"] is string, "status must be a JSON string");
            Check(parsed["error_category"] is string, "error_category must be a JSON string");
        }

        private static Dictionary<string, object> ParseJson(string json)
        {
            try
            {
                return new JavaScriptSerializer().DeserializeObject(json) as Dictionary<string, object>;
            }
            catch (Exception)
            {
                return null;
            }
        }

        private static string GetString(Dictionary<string, object> parsed, string key)
        {
            object value;
            if (!parsed.TryGetValue(key, out value) || value == null)
                return null;
            return value.ToString();
        }

        private static AutomationElement FindByControlType(AutomationElement root, string controlType, string name)
        {
            _lastTreeDump = string.Empty;
            AutomationElementCollection all = root.FindAll(TreeScope.Descendants, Condition.TrueCondition);
            StringBuilder dump = new StringBuilder();
            foreach (AutomationElement element in all)
            {
                AutomationElement.AutomationElementInformation info = element.Current;
                dump.Append("    ").Append(info.ControlType.ProgrammaticName)
                    .Append(" name='").Append(info.Name)
                    .Append("' automation_id='").Append(info.AutomationId).Append("'\n");
                if (info.ControlType.ProgrammaticName == controlType && info.Name == name)
                    return element;
            }
            _lastTreeDump = dump.ToString();
            return null;
        }

        private static string TreeDump()
        {
            return string.IsNullOrEmpty(_lastTreeDump)
                ? string.Empty
                : "\n  tree was:\n" + _lastTreeDump.TrimEnd('\n');
        }

        private static string ReadValue(AutomationElement element)
        {
            if (element == null)
                return null;
            object pattern;
            if (!element.TryGetCurrentPattern(ValuePattern.Pattern, out pattern))
                return null;
            return ((ValuePattern)pattern).Current.Value;
        }

        private static bool SpinUntil(Func<bool> condition, int timeoutMilliseconds)
        {
            Stopwatch stopwatch = Stopwatch.StartNew();
            while (stopwatch.ElapsedMilliseconds < timeoutMilliseconds)
            {
                if (condition())
                    return true;
                Thread.Sleep(25);
            }
            return condition();
        }

        private static string Sha256Hex(string text)
        {
            using (SHA256 sha = SHA256.Create())
            {
                byte[] hash = sha.ComputeHash(Encoding.UTF8.GetBytes(text));
                StringBuilder sb = new StringBuilder(64);
                for (int i = 0; i < hash.Length; i++)
                    sb.Append(hash[i].ToString("x2"));
                return sb.ToString();
            }
        }

        private static bool BytesEqual(byte[] left, byte[] right)
        {
            if (left.Length != right.Length)
                return false;
            for (int i = 0; i < left.Length; i++)
            {
                if (left[i] != right[i])
                    return false;
            }
            return true;
        }

        private static string FindRepoRoot()
        {
            string directory = AppDomain.CurrentDomain.BaseDirectory;
            for (int depth = 0; depth < 8 && !string.IsNullOrEmpty(directory); depth++)
            {
                if (File.Exists(Path.Combine(directory, "core", "text", "TextInjector.cs")))
                    return directory;
                string parent = Path.GetDirectoryName(directory.TrimEnd(Path.DirectorySeparatorChar));
                if (parent == directory)
                    break;
                directory = parent;
            }
            return null;
        }

        // ================================================================ harness

        private static void Case(string id, string title, Action body)
        {
            _caseCount++;
            Failures.Clear();
            Notes.Clear();

            Stopwatch stopwatch = Stopwatch.StartNew();
            string exception = null;
            try
            {
                body();
            }
            catch (Exception ex)
            {
                exception = ex.GetType().Name + ": " + ex.Message;
            }
            stopwatch.Stop();

            bool passed = exception == null && Failures.Count == 0;
            if (!passed)
                _failedCases++;

            Emit((passed ? "[PASS] " : "[FAIL] ") + id + "  (" + stopwatch.ElapsedMilliseconds + " ms)");
            Emit("       " + title);
            if (exception != null)
                Emit("       exception: " + exception);
            foreach (string failure in Failures)
                Emit("       - " + failure);
            foreach (string note in Notes)
                Emit("       note: " + note);
        }

        private static void Check(bool condition, string what)
        {
            if (!condition)
                Failures.Add(what);
        }

        private static void CheckEqual(object expected, object actual, string what)
        {
            bool equal = expected == null ? actual == null : expected.Equals(actual);
            if (!equal)
                Failures.Add(what + " — expected <" + Render(expected) + "> but was <" + Render(actual) + ">");
        }

        private static void Note(string text)
        {
            Notes.Add(text);
        }

        private static string Render(object value)
        {
            return value == null ? "null" : value.ToString();
        }

        private static void Emit(string line)
        {
            Output.Add(line);
            Console.WriteLine(line);
        }
    }
}
