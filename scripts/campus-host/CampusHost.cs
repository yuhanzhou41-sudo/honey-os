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
    private const int WatchIntervalSeconds = 600;

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

    // 仅识别表头含「星期一…星期日」的课表网格；按 colspan 对齐列，
    // 每格输出「星期|节次|内容」，不读取页面其他内容。
    private const string ExtractTimetableScript =
        @"(function(){
            function clean(t){ t=String(t==null?'':t); return t.replace(/[\|\t\n\r;]/g,' ').replace(/\s+/g,' ').trim(); }
            function dayOf(text){
              var t=clean(text).replace(/\s/g,'');
              var m=t.match(/^(?:星期|周)([一二三四五六日天])/);
              if(!m){ return null; }
              return '周'+(m[1]==='天'?'日':m[1]);
            }
            function cellsOf(row){
              var out=[], pos=0;
              for(var i=0;i<row.cells.length;i++){
                var cell=row.cells[i], span=cell.colSpan||1;
                out.push({start:pos,text:clean(cell.textContent)});
                pos+=span;
              }
              return out;
            }
            function scan(doc){
              var tables=doc.getElementsByTagName('table');
              for(var i=0;i<tables.length;i++){
                var tb=tables[i];
                if(tb.rows.length<3){ continue; }
                for(var h=0;h<3 && h<tb.rows.length;h++){
                  var head=cellsOf(tb.rows[h]), days={}, hits=0;
                  for(var c=0;c<head.length;c++){
                    var d=dayOf(head[c].text);
                    if(d){ days[head[c].start]=d; hits++; }
                  }
                  if(hits<3){ continue; }
                  var out=[];
                  for(var r=h+1;r<tb.rows.length;r++){
                    var rc=cellsOf(tb.rows[r]), label='';
                    for(var k=0;k<rc.length;k++){
                      if(dayOf(rc[k].text)===null){ label=rc[k].text; break; }
                    }
                    for(var k2=0;k2<rc.length;k2++){
                      var day=days[rc[k2].start];
                      if(!day){ continue; }
                      var detail=rc[k2].text;
                      if(!detail || detail===label){ continue; }
                      out.push([day,label,detail].join('|'));
                    }
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
              window.chrome.webview.postMessage('TIMETABLE'+'\t'+String(rows.length)+'\t'+rows.join('\t'));
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

    private static string BuildSnapshotJson(string source, string account, string[][] rows)
    {
        var sb = new StringBuilder();
        sb.Append("{\"schema\":\"campus-exams-snapshot/1\",\"account\":\"")
          .Append(JsonEscape(account))
          .Append("\",\"captured_at\":\"")
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

    private static string BuildTimetableJson(string source, string account, string[][] rows)
    {
        var sb = new StringBuilder();
        sb.Append("{\"schema\":\"campus-timetable-snapshot/1\",\"account\":\"")
          .Append(JsonEscape(account))
          .Append("\",\"captured_at\":\"")
          .Append(DateTime.Now.ToString("yyyy-MM-dd'T'HH:mm:sszzz"))
          .Append("\",\"source\":\"").Append(JsonEscape(source))
          .Append("\",\"row_count\":").Append(rows.Length).Append(",\"rows\":[");
        for (int i = 0; i < rows.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append("{\"day\":\"").Append(JsonEscape(rows[i][0]))
              .Append("\",\"period\":\"").Append(JsonEscape(rows[i][1]))
              .Append("\",\"detail\":\"").Append(JsonEscape(rows[i][2])).Append("\"}");
        }
        return sb.Append("]}").ToString();
    }

    // 账号标识只保留 ASCII 安全字符，同时作为 WebView2 profile 与快照文件名的一部分。
    private static string SafeProfile(string value)
    {
        var sb = new StringBuilder();
        foreach (char c in value ?? "")
        {
            if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
                || (c >= '0' && c <= '9') || c == '_' || c == '-')
                sb.Append(c);
            if (sb.Length >= 32) break;
        }
        return sb.ToString();
    }

    private static string SnapshotName(string stem, string profile)
    {
        return string.IsNullOrEmpty(profile)
            ? stem + ".latest.json"
            : stem + "." + profile + ".latest.json";
    }

    // 会话探活：只记录时间、域名与读取结果，不记录任何页面内容。
    private static void WriteWatch(string result, string host, int exams, int timetable)
    {
        try
        {
            string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "HoneyOS", "campus");
            Directory.CreateDirectory(dir);
            string path = Path.Combine(dir, "session-watch.jsonl");
            string line = "{\"at\":\"" + DateTime.Now.ToString("yyyy-MM-dd'T'HH:mm:sszzz")
                + "\",\"result\":\"" + JsonEscape(result)
                + "\",\"host\":\"" + JsonEscape(host)
                + "\",\"exams\":" + exams + ",\"timetable\":" + timetable + "}";
            File.AppendAllText(path, line + "\n", new UTF8Encoding(false));
        }
        catch { }
    }

    private static void WriteSnapshot(string fileName, string json)
    {
        string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "HoneyOS", "campus", "snapshots");
        Directory.CreateDirectory(dir);
        string target = Path.Combine(dir, fileName);
        string tmp = target + ".tmp";
        File.WriteAllText(tmp, json, new UTF8Encoding(false));
        if (File.Exists(target)) File.Delete(target);
        File.Move(tmp, target);
    }

    [STAThread]
    private static int Main(string[] args)
    {
        bool smoke = false;
        bool capture = false;
        bool watch = false;
        string profile = "";
        for (int i = 0; i < args.Length; i++)
        {
            string arg = args[i];
            if (arg == "--smoke") smoke = true;
            else if (arg == "--capture") capture = true;
            else if (arg == "--watch") { watch = true; capture = true; }
            else if (arg == "--profile" && i + 1 < args.Length) profile = SafeProfile(args[++i]);
            else return 2;
        }        Application.EnableVisualStyles();
        int result = 1;
        using (var window = new Form { Text = "HoneyOS · 校园连接验证", Width = 1000, Height = 720 })
        using (var browser = new WebView2 { Dock = DockStyle.Fill })
        using (var status = new Label { Dock = DockStyle.Top, Height = 32,
            Text = capture ? "请登录后分别打开 教务→考试查询 与 教务→我的课表；识别到表格后自动保存。"
                           : "正在启动独立校园窗口…" })
        using (var timeout = new Timer { Interval = 30000 })
        using (var poll = new Timer { Interval = 2000 })
        using (var heartbeat = new Timer { Interval = WatchIntervalSeconds * 1000 })
        {
            bool captured = false;
            bool capturedTimetable = false;
            int examCount = 0;
            int timetableCount = 0;
            DateTime captureDeadline = DateTime.UtcNow.AddSeconds(CaptureTimeoutSeconds);
            window.Controls.Add(browser);
            window.Controls.Add(status);
            timeout.Tick += delegate { timeout.Stop(); window.Close(); };
            poll.Tick += async delegate {
                if (!capture) { poll.Stop(); return; }
                if (!watch && captured && capturedTimetable) { poll.Stop(); return; }
                if (!watch && DateTime.UtcNow > captureDeadline)
                {
                    poll.Stop();
                    status.Text = "未检测到完整的考试/课表数据；可关闭窗口后重试。";
                    return;
                }
                try
                {
                    var current = browser.CoreWebView2;
                    if (current == null) return;
                    Uri here;
                    if (!Uri.TryCreate(current.Source, UriKind.Absolute, out here) ||
                        here.IdnHost != "jiaowu.cqmu.edu.cn") return;
                    if (!captured) await current.ExecuteScriptAsync(ExtractExamsScript);
                    if (!capturedTimetable) await current.ExecuteScriptAsync(ExtractTimetableScript);
                }
                catch { }
            };
            window.Shown += async delegate {
                try {
                    if (smoke) timeout.Start();
                    string profileDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                        "HoneyOS", "CampusHostProbe",
                        (smoke ? "runtime-check" : "official-login")
                        + (string.IsNullOrEmpty(profile) ? "" : "-" + profile));
                    var environment = await CoreWebView2Environment.CreateAsync(null, profileDir);
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
                                if (message == null) return;
                                bool isExams = message.StartsWith("EXAMS\t", StringComparison.Ordinal);
                                bool isTimetable = message.StartsWith("TIMETABLE\t", StringComparison.Ordinal);
                                if (!isExams && !isTimetable) return;
                                Uri origin;
                                if (!Uri.TryCreate(core.Source, UriKind.Absolute, out origin) ||
                                    origin.IdnHost != "jiaowu.cqmu.edu.cn") return;
                                string[] parts = message.Split('\t');
                                int count;
                                if (parts.Length < 3 || !int.TryParse(parts[1], out count) ||
                                    count <= 0 || count > CaptureMaxRows) return;
                                int width = isExams ? 4 : 3;
                                var rows = new string[count][];
                                for (int i = 0; i < count; i++)
                                {
                                    string[] cells = (i + 2 < parts.Length ? parts[i + 2] : "").Split('|');
                                    var row = new string[width];
                                    for (int cIdx = 0; cIdx < width; cIdx++)
                                    {
                                        string cell = cIdx < cells.Length ? cells[cIdx] : "";
                                        row[cIdx] = cell.Length > CaptureCellMax ? cell.Substring(0, CaptureCellMax) : cell;
                                    }
                                    rows[i] = row;
                                }
                                if (isExams)
                                {
                                    WriteSnapshot(SnapshotName("exams", profile),
                                        BuildSnapshotJson("https://jiaowu.cqmu.edu.cn:8080", profile, rows));
                                    captured = true;
                                    examCount = count;
                                }
                                else
                                {
                                    WriteSnapshot(SnapshotName("timetable", profile),
                                        BuildTimetableJson("https://jiaowu.cqmu.edu.cn:8080", profile, rows));
                                    capturedTimetable = true;
                                    timetableCount = count;
                                }
                                if (captured && capturedTimetable) poll.Stop();
                                status.Text = "已保存：考试 " + examCount + " 条、课表 " + timetableCount
                                    + " 条；可继续切换到另一个查询页，或关闭窗口。";
                            }
                            catch (Exception)
                            {
                                status.Text = "捕获失败；可留在考试查询页等待自动重试。";
                            }
                        };
                        poll.Start();
                        if (watch)
                        {
                            heartbeat.Tick += delegate {
                                try
                                {
                                    var live = browser.CoreWebView2;
                                    if (live == null) return;
                                    Uri here;
                                    string host = Uri.TryCreate(live.Source, UriKind.Absolute, out here)
                                        ? here.IdnHost : "";
                                    if (host == "jiaowu.cqmu.edu.cn")
                                    {
                                        WriteWatch("reload", host, examCount, timetableCount);
                                        live.Reload();
                                    }
                                    else
                                    {
                                        WriteWatch("login_required", host, examCount, timetableCount);
                                        status.Text = "会话可能已过期（当前停留：" + host + "）；请重新登录后继续。";
                                    }
                                }
                                catch { }
                            };
                            heartbeat.Start();
                            status.Text = "会话探活已开启：每 10 分钟记录一次结果，可最小化窗口。";
                        }
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
