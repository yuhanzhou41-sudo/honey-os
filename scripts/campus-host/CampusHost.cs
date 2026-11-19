using System;
using System.IO;
using System.Text;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal static class CampusHost
{
    private const string Portal = "https://my.cqmu.edu.cn/";
    private const int CaptureMaxRows = 200;
    private const int CaptureCellMax = 200;
    private const int CaptureTimeoutSeconds = 600;

    private static readonly string[] AllowedOrigins =
    {
        "https://my.cqmu.edu.cn", "http://my.cqmu.edu.cn",
        "https://cas.cqmu.edu.cn", "http://cas.cqmu.edu.cn",
        "https://jiaowu.cqmu.edu.cn", "http://jiaowu.cqmu.edu.cn",
        "https://jiaowu.cqmu.edu.cn:8080", "http://jiaowu.cqmu.edu.cn:8080",
    };

    private static bool Allowed(string target)
    {
        Uri uri;
        return Uri.TryCreate(target, UriKind.Absolute, out uri) &&
            (uri.Scheme == "https" || uri.Scheme == "http") && uri.UserInfo.Length == 0 &&
            Array.Exists(AllowedOrigins, allowed => allowed == uri.Scheme + "://" + uri.IdnHost +
                (uri.IsDefaultPort ? "" : ":" + uri.Port));
    }

    private static string Blocked(string target)
    {
        Uri uri;
        string origin = Uri.TryCreate(target, UriKind.Absolute, out uri) &&
            (uri.Scheme == "https" || uri.Scheme == "http")
            ? uri.Scheme + "://" + uri.IdnHost + (uri.IsDefaultPort ? "" : ":" + uri.Port)
            : "非网页目标";
        return "已阻止：" + origin + "；请勿输入账号。";
    }

    // 仅识别「课程名称/考试日期/考试安排/考试地点」四列表格；单元格脱敏（去分隔符、压缩空白），
    // 结果经 postMessage 单向上行，不读取页面其他内容。
    private const string ExtractExamsScript =
        @"(function(){
            function clean(t){ t=String(t==null?'':t); return t.replace(/[\|\t\n\r;]/g,' ').replace(/\s+/g,' ').trim(); }
            function scan(doc){
              var tables=doc.getElementsByTagName('table');
              for(var i=0;i<tables.length;i++){
                var tb=tables[i]; if(tb.rows.length<2) continue;
                for(var h=0;h<3 && h<tb.rows.length;h++){
                  var head=tb.rows[h]; var map={};
                  for(var c=0;c<head.cells.length;c++){
                    var t=clean(head.cells[c].textContent);
                    if(t=='课程名称'){map.course=c;} else if(t=='考试日期'){map.date=c;}
                    else if(t=='考试安排'){map.arr=c;} else if(t=='考试地点'){map.loc=c;}
                  }
                  if(map.date===undefined||map.loc===undefined){ continue; }
                  var out=[];
                  for(var r=h+1;r<tb.rows.length;r++){
                    var tr=tb.rows[r];
                    function cell(k){ return map[k]===undefined?'':clean(tr.cells[map[k]].textContent); }
                    var row=[cell('course'),cell('date'),cell('arr'),cell('loc')];
                    if(row.join('')===''){ continue; }
                    out.push(row.join('|'));
                  }
                  if(out.length>0){ return out; }
                }
              }
              return null;
            }
            var rows=scan(document);
            if(rows===null){
              try{
                for(var f=0;f<window.frames.length;f++){
                  rows=scan(window.frames[f].document);
                  if(rows!==null){ break; }
                }
              }catch(e){}
            }
            if(rows!==null && rows.length>0){
              window.chrome.webview.postMessage('EXAMS'+'\t'+String(rows.length)+'\t'+rows.join('\t'));
            }
        })();";

    private static string JsonEscape(string value)
    {
        var sb = new StringBuilder();
        foreach (char c in value)
        {
            if (c == '"') sb.Append("\\\"");
            else if (c == '\\') sb.Append("\\\\");
            else if (c == '\n') sb.Append("\\n");
            else if (c == '\r') sb.Append("\\r");
            else if (c == '\t') sb.Append("\\t");
            else if (c < ' ') sb.Append("\\u").Append(((int)c).ToString("x4"));
            else sb.Append(c);
        }
        return sb.ToString();
    }

    private static string BuildSnapshotJson(string source, string[][] rows)
    {
        var sb = new StringBuilder();
        sb.Append("{\"schema\":\"campus-exams-snapshot/1\",\"captured_at\":\"")
          .Append(DateTime.Now.ToString("yyyy-MM-dd'T'HH:mm:sszzz"))
          .Append("\",\"source\":\"").Append(JsonEscape(source))
          .Append("\",\"row_count\":").Append(rows.Length).Append(",\"rows\":[");
        for (int i = 0; i < rows.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append("{\"course\":\"").Append(JsonEscape(rows[i][0]))
              .Append("\",\"exam_date\":\"").Append(JsonEscape(rows[i][1]))
              .Append("\",\"arrangement\":\"").Append(JsonEscape(rows[i][2]))
              .Append("\",\"location\":\"").Append(JsonEscape(rows[i][3])).Append("\"}");
        }
        return sb.Append("]}").ToString();
    }

    private static void WriteSnapshot(string json)
    {
        string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "HoneyOS", "campus", "snapshots");
        Directory.CreateDirectory(dir);
        string target = Path.Combine(dir, "exams.latest.json");
        string tmp = target + ".tmp";
        File.WriteAllText(tmp, json, new UTF8Encoding(false));
        if (File.Exists(target)) File.Delete(target);
        File.Move(tmp, target);
    }

    [STAThread]
    private static int Main(string[] args)
    {
        bool smoke = args.Length == 1 && args[0] == "--smoke";
        bool capture = args.Length == 1 && args[0] == "--capture";
        if (args.Length != 0 && !smoke && !capture) return 2;
        Application.EnableVisualStyles();
        int result = 1;
        using (var window = new Form { Text = "HoneyOS · 校园连接验证", Width = 1000, Height = 720 })
        using (var browser = new WebView2 { Dock = DockStyle.Fill })
        using (var status = new Label { Dock = DockStyle.Top, Height = 32,
            Text = capture ? "请登录并进入 教务系统→考试查询；检测到考试表后自动保存。"
                           : "正在启动独立校园窗口…" })
        using (var timeout = new Timer { Interval = 30000 })
        using (var poll = new Timer { Interval = 2000 })
        {
            bool captured = false;
            DateTime captureDeadline = DateTime.UtcNow.AddSeconds(CaptureTimeoutSeconds);
            window.Controls.Add(browser);
            window.Controls.Add(status);
            timeout.Tick += delegate { timeout.Stop(); window.Close(); };
            poll.Tick += async delegate {
                if (!capture || captured) { poll.Stop(); return; }
                if (DateTime.UtcNow > captureDeadline)
                {
                    poll.Stop();
                    status.Text = "未检测到考试表；可关闭窗口后重试。";
                    return;
                }
                try
                {
                    var current = browser.CoreWebView2;
                    if (current == null) return;
                    Uri here;
                    if (!Uri.TryCreate(current.Source, UriKind.Absolute, out here) ||
                        here.IdnHost != "jiaowu.cqmu.edu.cn") return;
                    await current.ExecuteScriptAsync(ExtractExamsScript);
                }
                catch { }
            };
            window.Shown += async delegate {
                try {
                    if (smoke) timeout.Start();
                    string profile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                        "HoneyOS", "CampusHostProbe", smoke ? "runtime-check" : "official-login");
                    var environment = await CoreWebView2Environment.CreateAsync(null, profile);
                    await browser.EnsureCoreWebView2Async(environment);
                    var core = browser.CoreWebView2;
                    core.Settings.AreDevToolsEnabled = false;
                    core.Settings.AreDefaultContextMenusEnabled = false;
                    core.Settings.IsPasswordAutosaveEnabled = false;
                    core.Settings.IsGeneralAutofillEnabled = false;
                    core.Settings.AreHostObjectsAllowed = false;
                    core.DownloadStarting += (sender, request) => { request.Cancel = true; };
                    core.PermissionRequested += (sender, request) => { request.State = CoreWebView2PermissionState.Deny; };
                    core.LaunchingExternalUriScheme += (sender, request) => { request.Cancel = true; };
                    core.ServerCertificateErrorDetected += (sender, request) => { request.Action = CoreWebView2ServerCertificateErrorAction.Cancel; };
                    core.NavigationStarting += (sender, request) => {
                        request.Cancel = !Allowed(request.Uri);
                        status.Text = request.Cancel ? Blocked(request.Uri) : new Uri(request.Uri).GetLeftPart(UriPartial.Authority);
                    };
                    core.FrameNavigationStarting += (sender, request) => { request.Cancel = !Allowed(request.Uri); };
                    core.NewWindowRequested += (sender, request) => {
                        request.Handled = true;
                        if (Allowed(request.Uri)) core.Navigate(request.Uri);
                        else status.Text = Blocked(request.Uri);
                    };
                    if (capture)
                    {
                        core.Settings.IsWebMessageEnabled = true;
                        core.WebMessageReceived += delegate(object sender, CoreWebView2WebMessageReceivedEventArgs e) {
                            try
                            {
                                string message = null;
                                try { message = e.TryGetWebMessageAsString(); } catch { return; }
                                if (message == null || !message.StartsWith("EXAMS\t", StringComparison.Ordinal)) return;
                                Uri origin;
                                if (!Uri.TryCreate(core.Source, UriKind.Absolute, out origin) ||
                                    origin.IdnHost != "jiaowu.cqmu.edu.cn") return;
                                string[] parts = message.Split('\t');
                                int count;
                                if (parts.Length < 3 || !int.TryParse(parts[1], out count) ||
                                    count <= 0 || count > CaptureMaxRows) return;
                                var rows = new string[count][];
                                for (int i = 0; i < count; i++)
                                {
                                    string[] cells = (i + 2 < parts.Length ? parts[i + 2] : "").Split('|');
                                    var row = new string[4];
                                    for (int cIdx = 0; cIdx < 4; cIdx++)
                                    {
                                        string cell = cIdx < cells.Length ? cells[cIdx] : "";
                                        row[cIdx] = cell.Length > CaptureCellMax ? cell.Substring(0, CaptureCellMax) : cell;
                                    }
                                    rows[i] = row;
                                }
                                WriteSnapshot(BuildSnapshotJson("https://jiaowu.cqmu.edu.cn:8080", rows));
                                captured = true;
                                poll.Stop();
                                status.Text = "已捕获 " + count + " 条考试记录并保存；可关闭窗口。";
                            }
                            catch (Exception)
                            {
                                status.Text = "捕获失败；可留在考试查询页等待自动重试。";
                            }
                        };
                        poll.Start();
                    }
                    if (smoke) { result = 0; window.Close(); return; }
                    core.Navigate(Portal);
                    result = 0;
                } catch (Exception error) {
                    status.Text = "启动失败：" + error.GetType().Name;
                    if (smoke) window.Close();
                }
            };
            Application.Run(window);
        }
        return result;
    }
}
