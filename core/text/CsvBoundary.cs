// Karakuri — core/text (KARA-7: CP932 / Shift-JIS CSV boundary)
//
// The only place in Karakuri where a legacy Japanese encoding is touched.
//
// The rule from AGENTS.md / the frozen contract: UTF-8 end to end; CP932 (Shift-JIS) conversion
// happens only when a CSV file crosses the process boundary. Every routine below takes bytes and
// yields .NET strings (UTF-16, the in-memory form of UTF-8 text) or the reverse — nothing else in
// core/text calls into an encoding, which the QA test asserts structurally.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace Karakuri.Text
{
    /// <summary>CSV file encodings Karakuri understands.</summary>
    public enum CsvEncoding
    {
        /// <summary>Read: inspect the bytes. Write: resolve to <see cref="Cp932"/>.</summary>
        Auto,
        /// <summary>Windows code page 932 — Shift-JIS with the Microsoft vendor extensions.</summary>
        Cp932,
        /// <summary>UTF-8, with or without BOM.</summary>
        Utf8
    }

    /// <summary>Result of decoding a CSV: the parsed rows plus the encoding that was applied.</summary>
    public sealed class CsvReadResult : TextActionResult
    {
        /// <summary>Parsed rows; each row is a list of UTF-16 cell strings. Null on failure.</summary>
        public string[][] Rows { get; internal set; }

        /// <summary>The encoding actually applied (never <see cref="CsvEncoding.Auto"/>). Null on failure.</summary>
        public CsvEncoding? ResolvedEncoding { get; internal set; }
    }

    /// <summary>Result of encoding rows for CSV output, optionally persisted to disk.</summary>
    public sealed class CsvWriteResult : TextActionResult
    {
        /// <summary>Encoded file bytes. Null on failure.</summary>
        public byte[] Data { get; internal set; }

        /// <summary>Where the bytes were written, or null when only in-memory encoding was requested.</summary>
        public string OutputPath { get; internal set; }

        /// <summary>Number of rows encoded. 0 on failure.</summary>
        public int RowsWritten { get; internal set; }

        /// <summary>0-based row of the first cell that could not be encoded. Null on success.</summary>
        public int? RowIndex { get; internal set; }

        /// <summary>0-based column of the first cell that could not be encoded. Null on success.</summary>
        public int? ColumnIndex { get; internal set; }

        /// <summary>
        /// The text that could not be encoded (the full surrogate pair when it is a non-BMP
        /// character), or null on success. Extracted from the cell at the offset the encoder
        /// reported, because EncoderFallbackException.CharUnknown comes back as U+0000 for
        /// characters outside the BMP.
        /// </summary>
        public string OffendingText { get; internal set; }
    }

    /// <summary>
    /// CSV read/write with encoding conversion confined to these entry points.
    ///
    /// Reading is strict: a byte that is not valid in the detected encoding fails the read with
    /// <c>error_category: os_generic</c> and the offending offset, rather than substituting '?' or
    /// U+FFFD. Writing is strict too: a character with no CP932 representation fails the write with
    /// the cell located, and nothing is written to disk. Strictness is what makes "no dropped
    /// characters" a guarantee instead of a hope.
    /// </summary>
    public static class CsvBoundary
    {
        private const string FieldSeparator = ",";
        private const string RecordSeparator = "\r\n";

        private static readonly Encoding Cp932Strict = CreateCp932();
        private static readonly Encoding Utf8Strict = new UTF8Encoding(false, true);

        private static Encoding CreateCp932()
        {
            return Encoding.GetEncoding(932, EncoderFallback.ExceptionFallback, DecoderFallback.ExceptionFallback);
        }

        /// <summary>CP932 (Shift-JIS) encoder/decoder used by this module, strict on both sides.</summary>
        public static Encoding Cp932 { get { return Cp932Strict; } }

        // ---------------------------------------------------------------- read

        /// <summary>Read a CSV file, detecting its encoding from the bytes.</summary>
        public static CsvReadResult Read(string path)
        {
            return Read(path, CsvEncoding.Auto);
        }

        /// <summary>Read a CSV file. Conversion happens here and nowhere else.</summary>
        public static CsvReadResult Read(string path, CsvEncoding encoding)
        {
            if (path == null)
                throw new ArgumentNullException("path");

            byte[] data;
            try
            {
                data = File.ReadAllBytes(path);
            }
            catch (IOException ex)
            {
                return ReadFailure("Could not read '" + path + "': " + ex.Message);
            }
            catch (UnauthorizedAccessException ex)
            {
                return ReadFailure("Could not read '" + path + "': " + ex.Message);
            }

            return DecodeRows(data, encoding);
        }

        /// <summary>Decode and parse CSV bytes. This is the read half of the encoding boundary.</summary>
        public static CsvReadResult DecodeRows(byte[] data, CsvEncoding encoding)
        {
            if (data == null)
                throw new ArgumentNullException("data");

            int offset;
            string detectedProblem;
            Encoding resolved = ResolveReadEncoding(data, encoding, out offset, out detectedProblem);
            if (resolved == null)
                return ReadFailure(detectedProblem);

            string text;
            try
            {
                int length = data.Length - offset;
                text = length <= 0 ? string.Empty : resolved.GetString(data, offset, length);
            }
            catch (DecoderFallbackException ex)
            {
                return ReadFailure(
                    "Byte offset " + ex.Index + " is not valid " + NameOf(resolved) + ". The CSV was not decoded; "
                  + "no bytes were substituted. Re-export the file or pass an explicit encoding.");
            }
            catch (ArgumentException ex)
            {
                return ReadFailure("Could not decode the CSV as " + NameOf(resolved) + ": " + ex.Message);
            }

            CsvReadResult result = new CsvReadResult();
            result.SucceedAs("Decoded and parsed as " + NameOf(resolved) + ".");
            result.ResolvedEncoding = ToCsvEncoding(resolved);
            result.Rows = ParseRecords(text);
            return result;
        }

        // ---------------------------------------------------------------- write

        /// <summary>
        /// Encode rows to CSV bytes in memory. <see cref="CsvEncoding.Auto"/> resolves to CP932,
        /// the encoding legacy Japanese back-office applications expect from a CSV.
        /// </summary>
        public static CsvWriteResult EncodeRows(IEnumerable<string[]> rows, CsvEncoding encoding)
        {
            if (rows == null)
                throw new ArgumentNullException("rows");

            Encoding target = encoding == CsvEncoding.Utf8 ? Utf8Strict : Cp932Strict;

            StringBuilder builder = new StringBuilder(256);
            int rowIndex = -1;
            foreach (string[] row in rows)
            {
                rowIndex++;
                if (row == null)
                    return EncodeFailure(rowIndex, 0, null, "Row " + rowIndex + " is null.");

                for (int columnIndex = 0; columnIndex < row.Length; columnIndex++)
                {
                    string cell = row[columnIndex] ?? string.Empty;
                    try
                    {
                        target.GetBytes(cell);
                    }
                    catch (EncoderFallbackException ex)
                    {
                        string offender = DescribeOffender(cell, ex);
                        return EncodeFailure(rowIndex, columnIndex, offender,
                            "Cell (row " + rowIndex + ", column " + columnIndex + ") contains " + Escape(offender)
                          + ", which has no " + NameOf(target) + " representation. The file was not written, so "
                          + "no character can be silently replaced.");
                    }

                    if (columnIndex > 0)
                        builder.Append(FieldSeparator);
                    builder.Append(EscapeField(cell));
                }
                builder.Append(RecordSeparator);
            }

            CsvWriteResult result = new CsvWriteResult();
            result.SucceedAs("Encoded " + (rowIndex + 1) + " row(s) as " + NameOf(target) + ".");
            result.Data = target.GetBytes(builder.ToString());
            result.RowsWritten = rowIndex + 1;
            return result;
        }

        /// <summary>Encode rows and write them to <paramref name="path"/> in one non-rewriting pass.</summary>
        public static CsvWriteResult Write(string path, IEnumerable<string[]> rows, CsvEncoding encoding)
        {
            if (path == null)
                throw new ArgumentNullException("path");

            CsvWriteResult encoded = EncodeRows(rows, encoding);
            if (!encoded.Success)
                return encoded;

            try
            {
                string directory = Path.GetDirectoryName(Path.GetFullPath(path));
                if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
                    Directory.CreateDirectory(directory);
                File.WriteAllBytes(path, encoded.Data);
            }
            catch (IOException ex)
            {
                return EncodeFailure(-1, -1, null, "Could not write '" + path + "': " + ex.Message);
            }
            catch (UnauthorizedAccessException ex)
            {
                return EncodeFailure(-1, -1, null, "Could not write '" + path + "': " + ex.Message);
            }

            encoded.OutputPath = path;
            return encoded;
        }

        // ---------------------------------------------------------------- encoding detection

        private static Encoding ResolveReadEncoding(byte[] data, CsvEncoding encoding, out int offset, out string problem)
        {
            problem = null;
            offset = 0;

            // The caller pinned the encoding: honour it and let a bad byte fail in the decoder
            // with an exact offset rather than being second-guessed here.
            if (encoding == CsvEncoding.Cp932)
                return Cp932Strict;

            if (HasUtf16Bom(data))
            {
                problem = "This CSV starts with a UTF-16 byte-order mark. Karakuri exchanges UTF-8 and "
                        + "CP932/Shift-JIS only (UTF-8 end to end, CP932 at the CSV boundary), so UTF-16 "
                        + "files are rejected rather than guessed at. Re-save the file as UTF-8 or CP932.";
                return null;
            }

            if (encoding == CsvEncoding.Utf8)
            {
                offset = HasUtf8Bom(data) ? 3 : 0;
                return Utf8Strict;
            }

            // Auto detection: an explicit UTF-8 BOM settles it, otherwise the bytes must survive a
            // strict UTF-8 decode. ASCII-only files satisfy both and decode identically either way;
            // CP932 Japanese text almost never survives a strict UTF-8 decode.
            if (HasUtf8Bom(data))
            {
                offset = 3;
                return Utf8Strict;
            }

            try
            {
                Utf8Strict.GetString(data, 0, data.Length);
                return Utf8Strict;
            }
            catch (DecoderFallbackException)
            {
                return Cp932Strict;
            }
        }

        private static bool HasUtf8Bom(byte[] data)
        {
            return data.Length >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF;
        }

        private static bool HasUtf16Bom(byte[] data)
        {
            return (data.Length >= 2 && data[0] == 0xFF && data[1] == 0xFE)
                || (data.Length >= 2 && data[0] == 0xFE && data[1] == 0xFF);
        }

        private static CsvEncoding ToCsvEncoding(Encoding resolved)
        {
            return object.ReferenceEquals(resolved, Utf8Strict) ? CsvEncoding.Utf8 : CsvEncoding.Cp932;
        }

        private static string NameOf(Encoding encoding)
        {
            return object.ReferenceEquals(encoding, Utf8Strict) ? "UTF-8" : "CP932/Shift-JIS";
        }

        // ---------------------------------------------------------------- helpers

        private static CsvReadResult ReadFailure(string message)
        {
            CsvReadResult result = new CsvReadResult();
            result.FailAs(TextActionResult.CategoryOsGeneric, null, message);
            return result;
        }

        private static CsvWriteResult EncodeFailure(int rowIndex, int columnIndex, string offendingText, string message)
        {
            CsvWriteResult result = new CsvWriteResult();
            result.FailAs(TextActionResult.CategoryOsGeneric, null, message);
            if (rowIndex >= 0)
            {
                result.RowIndex = rowIndex;
                result.ColumnIndex = columnIndex;
                result.OffendingText = offendingText;
            }
            return result;
        }

        /// <summary>
        /// The exact input the encoder choked on. EncoderFallbackException only carries an index and
        /// a CharUnknown that is U+0000 for non-BMP characters, so the text is recovered from the
        /// cell itself at that index (a whole surrogate pair when one starts there).
        /// </summary>
        private static string DescribeOffender(string cell, EncoderFallbackException ex)
        {
            int index = ex.Index;
            if (index >= 0 && index < cell.Length)
            {
                int length = 1;
                if (index + 1 < cell.Length
                    && char.IsHighSurrogate(cell[index])
                    && char.IsLowSurrogate(cell[index + 1]))
                {
                    length = 2;
                }
                return cell.Substring(index, length);
            }
            if (ex.CharUnknown != '\0')
                return ex.CharUnknown.ToString();
            return "?";
        }

        /// <summary>JSON-ish quoting so a control character or a quote reads safely in a message.</summary>
        private static string Escape(string value)
        {
            return "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
        }

        private static string EscapeField(string cell)
        {
            if (cell.Length == 0)
                return string.Empty;
            if (cell.IndexOfAny(new char[] { '"', ',', '\r', '\n' }) < 0)
                return cell;
            return "\"" + cell.Replace("\"", "\"\"") + "\"";
        }

        /// <summary>RFC 4180 record parsing: quoted fields, doubled quotes, CRLF or LF records.</summary>
        private static string[][] ParseRecords(string text)
        {
            List<string[]> records = new List<string[]>();
            List<string> fields = new List<string>();
            StringBuilder cell = new StringBuilder();
            bool inQuotes = false;
            int i = 0;

            while (i < text.Length)
            {
                char c = text[i];

                if (inQuotes)
                {
                    if (c == '"')
                    {
                        if (i + 1 < text.Length && text[i + 1] == '"')
                        {
                            cell.Append('"');
                            i += 2;
                            continue;
                        }
                        inQuotes = false;
                        i++;
                        continue;
                    }
                    cell.Append(c);
                    i++;
                    continue;
                }

                if (c == '"')
                {
                    inQuotes = true;
                    i++;
                    continue;
                }
                if (c == ',')
                {
                    fields.Add(cell.ToString());
                    cell.Length = 0;
                    i++;
                    continue;
                }
                if (c == '\r' || c == '\n')
                {
                    fields.Add(cell.ToString());
                    cell.Length = 0;
                    records.Add(fields.ToArray());
                    fields.Clear();
                    if (c == '\r' && i + 1 < text.Length && text[i + 1] == '\n')
                        i += 2;
                    else
                        i++;
                    continue;
                }

                cell.Append(c);
                i++;
            }

            if (cell.Length > 0 || fields.Count > 0)
            {
                fields.Add(cell.ToString());
                records.Add(fields.ToArray());
            }

            return records.ToArray();
        }
    }
}
