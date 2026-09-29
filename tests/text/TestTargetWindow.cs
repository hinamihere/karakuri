// Karakuri — tests/text (KARA-7)
//
// The QA target window: a real Win32 window whose text fields are genuine Win32 EDIT controls
// (WinForms TextBox wraps USER32 'Edit'), so the UIA path under test is the same one Yayoi,
// Bugyo and SAP GUI expose — ControlType.Edit + IValueProvider via the Win32 UIA proxy.
//
// Every field subclasses TextBox and counts the window messages it receives, which is what lets
// the QA test prove the negative claim directly: after ValuePattern.SetValue there must be zero
// WM_KEYDOWN / WM_CHAR and zero WM_IME_*COMPOSITION messages, i.e. no keystrokes and no IME
// composition dialog could possibly have occurred.
//
// Note on coordinates: the points below are this fixture's own control layout inside its own
// window. Karakuri never aims at screen coordinates — that rule governs automation, not a test
// app arranging its own children.

using System;
using System.Drawing;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace Karakuri.Tests.Text
{
    /// <summary>Window-message counters, read from the test thread through <see cref="Copy"/>.</summary>
    public sealed class MessageCounters
    {
        public int SetText;             // WM_SETTEXT      0x000C — buffer write
        public int ReplaceSel;          // EM_REPLACESEL   0x00C2 — buffer write
        public int KeyDown;             // WM_KEYDOWN/UP, WM_SYSKEYDOWN/UP
        public int CharMsg;             // WM_CHAR, WM_SYSCHAR
        public int ImeStart;            // WM_IME_STARTCOMPOSITION
        public int ImeComposition;      // WM_IME_COMPOSITION
        public int ImeEnd;              // WM_IME_ENDCOMPOSITION
        public int ImeChar;             // WM_IME_CHAR
        public int ImeNotify;           // WM_IME_NOTIFY  (context status; informational)
        public int InputLangChange;     // WM_INPUTLANGCHANGE (informational)

        /// <summary>Keyboard messages that would represent typed input.</summary>
        public int KeyboardTotal { get { return KeyDown + CharMsg; } }

        /// <summary>Messages that can only appear while an IME composition is open.</summary>
        public int CompositionTotal { get { return ImeStart + ImeComposition + ImeEnd + ImeChar; } }

        public int BufferWriteTotal { get { return SetText + ReplaceSel; } }

        public MessageCounters Copy()
        {
            return new MessageCounters
            {
                SetText = Interlocked.CompareExchange(ref SetText, 0, 0),
                ReplaceSel = Interlocked.CompareExchange(ref ReplaceSel, 0, 0),
                KeyDown = Interlocked.CompareExchange(ref KeyDown, 0, 0),
                CharMsg = Interlocked.CompareExchange(ref CharMsg, 0, 0),
                ImeStart = Interlocked.CompareExchange(ref ImeStart, 0, 0),
                ImeComposition = Interlocked.CompareExchange(ref ImeComposition, 0, 0),
                ImeEnd = Interlocked.CompareExchange(ref ImeEnd, 0, 0),
                ImeChar = Interlocked.CompareExchange(ref ImeChar, 0, 0),
                ImeNotify = Interlocked.CompareExchange(ref ImeNotify, 0, 0),
                InputLangChange = Interlocked.CompareExchange(ref InputLangChange, 0, 0)
            };
        }

        public string Describe()
        {
            return "WM_SETTEXT=" + SetText
                 + " EM_REPLACESEL=" + ReplaceSel
                 + " KEY=" + KeyboardTotal
                 + " IME_COMPOSITION=" + CompositionTotal
                 + " WM_IME_NOTIFY=" + ImeNotify
                 + " WM_INPUTLANGCHANGE=" + InputLangChange;
        }
    }

    /// <summary>A Win32 EDIT control that records every message routed to its window procedure.</summary>
    public sealed class RecordingTextBox : TextBox
    {
        public MessageCounters Counters;

        protected override void WndProc(ref Message m)
        {
            MessageCounters counters = Counters;
            if (counters != null)
            {
                switch (m.Msg)
                {
                    case 0x000C: counters.SetText++; break;            // WM_SETTEXT
                    case 0x00C2: counters.ReplaceSel++; break;         // EM_REPLACESEL
                    case 0x0100: counters.KeyDown++; break;            // WM_KEYDOWN
                    case 0x0101: counters.KeyDown++; break;            // WM_KEYUP
                    case 0x0102: counters.CharMsg++; break;            // WM_CHAR
                    case 0x0104: counters.KeyDown++; break;            // WM_SYSKEYDOWN
                    case 0x0105: counters.KeyDown++; break;            // WM_SYSKEYUP
                    case 0x0106: counters.CharMsg++; break;            // WM_SYSCHAR
                    case 0x010D: counters.ImeStart++; break;           // WM_IME_STARTCOMPOSITION
                    case 0x010E: counters.ImeEnd++; break;             // WM_IME_ENDCOMPOSITION
                    case 0x010F: counters.ImeComposition++; break;     // WM_IME_COMPOSITION
                    case 0x0286: counters.ImeChar++; break;            // WM_IME_CHAR
                    case 0x0282: counters.ImeNotify++; break;          // WM_IME_NOTIFY
                    case 0x0050: counters.InputLangChange++; break;    // WM_INPUTLANGCHANGE
                }
            }
            base.WndProc(ref m);
        }
    }

    /// <summary>
    /// A small Japanese back-office style form: an empty date field, a memo field, a read-only
    /// field, and a panel that exposes no ValuePattern at all.
    /// </summary>
    public sealed class JapaneseEntryForm : Form
    {
        public readonly MessageCounters Counters = new MessageCounters();
        public RecordingTextBox DateField;
        public RecordingTextBox MemoField;
        public RecordingTextBox ReadOnlyField;
        public Panel ParameterPane;

        public JapaneseEntryForm()
        {
            Text = "弥生会計 2026 - 仕訳入力";
            ClientSize = new Size(420, 260);
            StartPosition = FormStartPosition.WindowsDefaultLocation;

            DateField = NewField("納品日");
            DateField.Location = new Point(16, 16);

            MemoField = NewField("摘要");
            MemoField.Location = new Point(16, 56);

            ReadOnlyField = NewField("出力先");
            ReadOnlyField.ReadOnly = true;
            ReadOnlyField.Text = "既定";
            ReadOnlyField.Location = new Point(16, 96);

            ParameterPane = new Panel();
            ParameterPane.AccessibleName = "検索条件";
            ParameterPane.Location = new Point(16, 136);
            ParameterPane.Size = new Size(220, 70);

            Controls.Add(DateField);
            Controls.Add(MemoField);
            Controls.Add(ReadOnlyField);
            Controls.Add(ParameterPane);
        }

        private static RecordingTextBox NewField(string accessibleName)
        {
            RecordingTextBox box = new RecordingTextBox();
            box.AccessibleName = accessibleName;
            box.Size = new Size(180, 24);
            return box;
        }
    }

    /// <summary>Runs <see cref="JapaneseEntryForm"/> on its own STA thread with a live message pump.</summary>
    public sealed class TargetWindowHost : IDisposable
    {
        private Thread _thread;
        private ManualResetEvent _ready;
        private JapaneseEntryForm _form;
        private volatile IntPtr _handle;

        public IntPtr WindowHandle { get { return _handle; } }
        public JapaneseEntryForm Form { get { return _form; } }

        public void Start()
        {
            _ready = new ManualResetEvent(false);
            _thread = new Thread(Run);
            _thread.SetApartmentState(ApartmentState.STA);
            _thread.IsBackground = true;
            _thread.Name = "karakuri-qa-target";
            _thread.Start();

            if (!_ready.WaitOne(15000))
                throw new InvalidOperationException("The QA target window did not appear within 15 s.");

            // Give the window a moment to finish mapping before a UIA client walks it.
            Thread.Sleep(250);
        }

        private void Run()
        {
            try
            {
                _form = new JapaneseEntryForm();
                foreach (Control control in _form.Controls)
                {
                    RecordingTextBox box = control as RecordingTextBox;
                    if (box != null)
                        box.Counters = _form.Counters;
                }
                _form.Shown += delegate { _handle = _form.Handle; _ready.Set(); };
                Application.Run(_form);
            }
            finally
            {
                if (_ready != null)
                    _ready.Set();
            }
        }

        /// <summary>Destroys the target window and joins its thread (used by the stale-handle test).</summary>
        public void CloseWindow()
        {
            JapaneseEntryForm form = _form;
            if (form != null && form.IsHandleCreated)
            {
                try
                {
                    form.BeginInvoke((Action)delegate { form.Close(); });
                }
                catch (ObjectDisposedException)
                {
                    // already gone
                }
                catch (InvalidOperationException)
                {
                    // handle torn down concurrently
                }
            }

            if (_thread != null)
                _thread.Join(10000);
        }

        public void Dispose()
        {
            CloseWindow();
        }
    }
}
