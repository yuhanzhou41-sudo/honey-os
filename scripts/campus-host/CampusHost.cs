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
              window.chrome.webview.postMessage('EXAMS'+'\t'+String(rows.length)+'\t'+rows.join('\t')+'\t'+clicked());
            }
            function clicked(){
              try{
                var v=localStorage.getItem('__honeyosClick')||'';
                return clean(v).substring(0,30);
              }catch(e){ return ''; }
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
              window.chrome.webview.postMessage('TIMETABLE'+'\t'+String(rows.length)+'\t'+rows.join('\t')+'\t'+clicked());
            }
            function clicked(){
              try{
                var v=localStorage.getItem('__honeyosClick')||'';
                return clean(v).substring(0,30);
              }catch(e){ return ''; }
            }
        })();";

    private const string EamsHome = "https://jiaowu.cqmu.edu.cn:8080/eams/home.action";

    // 仅识别表头含「课程名称/成绩」的成绩表；输出「课程|成绩|学分|学期」。
    private const string ExtractGradesScript =
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
                    if(t.indexOf('课程名称')>=0||t==='课程'){ if(map.course===undefined) map.course=c; }
                    else if(t.indexOf('成绩')>=0||t==='分数'){ if(map.score===undefined) map.score=c; }
                    else if(t.indexOf('学分')>=0){ if(map.credit===undefined) map.credit=c; }
                    else if(t.indexOf('学期')>=0){ if(map.term===undefined) map.term=c; }
                  }
                  if(map.course===undefined||map.score===undefined){ continue; }
                  var out=[];
                  for(var r=h+1;r<tb.rows.length;r++){
                    var tr=tb.rows[r];
                    function cell(k){ return map[k]===undefined?'':clean(tr.cells[map[k]].textContent); }
                    var row=[cell('course'),cell('score'),cell('credit'),cell('term')];
                    if(!row[0]){ continue; }
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
              window.chrome.webview.postMessage('GRADES'+'\t'+String(rows.length)+'\t'+rows.join('\t')+'\t'+clicked());
            }
            function clicked(){
              try{
                var v=localStorage.getItem('__honeyosClick')||'';
                return clean(v).substring(0,30);
              }catch(e){ return ''; }
            }
        })();";

    // 记录用户点击的菜单文字（最多两步），用于下次自动回放。
    // 教务系统地址栏不随页面变化，只能靠点菜单；课表要先点「我的课表」再点「学生课表」。
    private const string ClickRecorderScript =
        @"(function(){
            if(window.__honeyosBound){ return 'BOUND'; }
            window.__honeyosBound=true;
            document.addEventListener('click', function(e){
              var n=e.target;
              while(n && n!==document.body){
                var tag=n.tagName;
                if(tag==='A'||tag==='LI'||tag==='SPAN'||tag==='LABEL'){
                  var t=String(n.innerText||n.textContent||'').replace(/\s+/g,' ').trim();
                    if(t && t.length<=30){
                    try{ localStorage.setItem('__honeyosClick', t); }catch(err){}
                    return;
                  }
                }
                n=n.parentElement;
              }
            }, true);
            return 'BOUND';
        })();";

    private static string ReplayScript(string target)
    {
        string safe = target.Replace("\\", "\\\\").Replace("'", "\\'");
        return @"(function(target){
            function txt(e){ return String(e.innerText||e.textContent||'').replace(/\s+/g,' ').trim(); }
            function norm(s){ return String(s||'').replace(/\s+/g,''); }
            var want=norm(target);
            function ownLabel(r){
              var n=r.nextSibling, guard=0;
              while(n && guard++<4){
                if(n.nodeType===3){ var t=norm(n.nodeValue); if(t){ return t; } }
                else if(n.nodeType===1){ var t2=norm(txt(n)); if(t2){ return t2.substring(0,20); } }
                n=n.nextSibling;
              }
              n=r.previousSibling; guard=0;
              while(n && guard++<4){
                if(n.nodeType===3){ var t3=norm(n.nodeValue); if(t3){ return t3; } }
                else if(n.nodeType===1){ var t4=norm(txt(n)); if(t4){ return t4.substring(0,20); } }
                n=n.previousSibling;
              }
              return '';
            }
            function byRadio(doc){
              var rs=[].slice.call(doc.querySelectorAll('input[type=radio]'));
              for(var i=0;i<rs.length;i++){
                var own=ownLabel(rs[i]);
                if(!own || own.length>16){ continue; }
                if(own.indexOf(want)!==0){ continue; }
                if(!rs[i].checked){ rs[i].click(); }
                return rs[i].checked ? 'RADIO:'+own : 'UNCHECKED:'+own;
              }
              return null;
            }
            function hitIn(doc){
              var nodes=[].slice.call(doc.querySelectorAll('a,label'));
              for(var i=0;i<nodes.length;i++){
                var t=txt(nodes[i]);
                if(t && t.length<=40 && t.indexOf(target)>=0){ return nodes[i]; }
              }
              nodes=[].slice.call(doc.querySelectorAll('li,span,td,div'));
              for(var j=0;j<nodes.length;j++){
                var t2=txt(nodes[j]);
                if(t2 && t2.length<=30 && t2.indexOf(target)>=0){ return nodes[j]; }
              }
              return null;
            }
            function attempt(doc){
              var r=byRadio(doc);
              if(r){ return r; }
              var hit=hitIn(doc);
              if(!hit){ return null; }
              var radio=hit.querySelector ? hit.querySelector('input[type=radio]') : null;
              if(radio){
                if(!radio.checked){ radio.click(); }
                return radio.checked ? 'RADIO:'+txt(hit) : 'UNCHECKED:'+txt(hit);
              }
              hit.click();
              return 'CLICKED:'+txt(hit);
            }
            var res=attempt(document);
            if(res){ return res; }
            for(var f=0;f<window.frames.length;f++){
              try{
                var fr=attempt(window.frames[f].document);
                if(fr){ return fr; }
              }catch(e){}
            }
            return 'NOTFOUND';
        })('" + safe + @"');";
    }

    // 诊断：只导出表格结构（表头文字与行列数），不导出任何课程内容。
    private const string DiagnoseScript =
        @"(function(){
            function clean(t){ return String(t==null?'':t).replace(/[\|\t\n\r;]/g,' ').replace(/\s+/g,' ').trim(); }
            function head(tb){
              var out=[];
              for(var r=0;r<tb.rows.length && r<2;r++){
                var cells=[];
                for(var c=0;c<tb.rows[r].cells.length && c<12;c++){
                  cells.push(clean(tb.rows[r].cells[c].textContent).substring(0,12));
                }
                out.push(cells.join('/'));
              }
              return out.join(' || ');
            }
            var parts=[];
            var tables=document.getElementsByTagName('table');
            parts.push('tables='+tables.length+' frames='+window.frames.length);
            for(var i=0;i<tables.length && parts.length<7;i++){
              parts.push('['+i+'] rows='+tables[i].rows.length+' head='+head(tables[i]));
            }
            return parts.join(' ;; ');
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

    private static string BuildGradesJson(string source, string account, string[][] rows)
    {
        var sb = new StringBuilder();
        sb.Append("{\"schema\":\"campus-grades-snapshot/1\",\"account\":\"")
          .Append(JsonEscape(account))
          .Append("\",\"captured_at\":\"")
          .Append(DateTime.Now.ToString("yyyy-MM-dd'T'HH:mm:sszzz"))
          .Append("\",\"source\":\"").Append(JsonEscape(source))
          .Append("\",\"row_count\":").Append(rows.Length).Append(",\"rows\":[");
        for (int i = 0; i < rows.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append("{\"course\":\"").Append(JsonEscape(rows[i][0]))
              .Append("\",\"score\":\"").Append(JsonEscape(rows[i][1]))
              .Append("\",\"credit\":\"").Append(JsonEscape(rows[i][2]))
              .Append("\",\"term\":\"").Append(JsonEscape(rows[i][3])).Append("\"}");
        }
        return sb.Append("]}").ToString();
    }
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

    // 自动化：记住成功捕获过的页面地址，下次直接导航过去。
    private static string NavPath(string profile, string kind)
    {
        string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "HoneyOS", "campus");
        return Path.Combine(dir, string.IsNullOrEmpty(profile)
            ? "nav." + kind + ".txt"
            : "nav." + profile + "." + kind + ".txt");
    }

    private static void SaveNav(string profile, string kind, string value)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(value)) return;
            string path = NavPath(profile, kind);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllText(path, value.Trim(), new UTF8Encoding(false));
        }
        catch { }
    }

    private static string LoadNav(string profile, string kind)
    {
        try
        {
            string path = NavPath(profile, kind);
            if (!File.Exists(path)) return "";
            return File.ReadAllText(path).Trim();
        }
        catch { return ""; }
    }

    private static bool NavExists(string profile, string kind)
    {
        try { return File.Exists(NavPath(profile, kind)); }
        catch { return false; }
    }

    private static bool IsUrlNav(string value)
    {
        Uri parsed;
        return Uri.TryCreate(value, UriKind.Absolute, out parsed) && Allowed(value);
    }

    private static void Trace(string message)
    {
        try
        {
            string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "HoneyOS", "campus");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "host.log"),
                DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + message + "\n",
                new UTF8Encoding(false));
        }
        catch { }
    }

    private static void CloseLater(Form window, int milliseconds)
    {
        var timer = new Timer { Interval = milliseconds };
        timer.Tick += delegate { timer.Stop(); timer.Dispose(); window.Close(); };
        timer.Start();
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
        bool auto = false;
        string profile = "";
        for (int i = 0; i < args.Length; i++)
        {
            string arg = args[i];
            if (arg == "--smoke") smoke = true;
            else if (arg == "--capture") capture = true;
            else if (arg == "--auto") { auto = true; capture = true; }
            else if (arg == "--profile" && i + 1 < args.Length) profile = SafeProfile(args[++i]);
            else return 2;
        }
        Application.EnableVisualStyles();
        Trace("main args=" + string.Join(",", args));
        AppDomain.CurrentDomain.UnhandledException += (sender, e) =>
            Trace("unhandled " + e.ExceptionObject);
        int result = 1;
        using (var window = new Form { Text = "HoneyOS · 校园连接验证", Width = 1000, Height = 720 })
        using (var browser = new WebView2 { Dock = DockStyle.Fill })
        using (var status = new Label { Dock = DockStyle.Top, Height = 32,
            Text = capture ? "请登录后分别打开 教务→考试查询 与 教务→我的课表；识别到表格后自动保存。"
                           : "正在启动独立校园窗口…" })
        using (var timeout = new Timer { Interval = 30000 })
        using (var poll = new Timer { Interval = 2000 })
        {
            bool captured = false;
            bool capturedTimetable = false;
            bool capturedGrades = false;
            int examCount = 0;
            int timetableCount = 0;
            int gradeCount = 0;
            int autoAttempts = 0;
            DateTime autoRetryAt = DateTime.MinValue;
            int clickAttempts = 0;
            DateTime clickRetryAt = DateTime.MinValue;
            int examClickStep = 0;
            int timetableClickStep = 0;
            int gradesClickStep = 0;
            bool diagnoseDone = false;
            DateTime diagnoseAt = DateTime.MinValue;
            string autoExams = auto ? LoadNav(profile, "exams") : "";
            string autoTimetable = auto ? LoadNav(profile, "timetable") : "";
            string autoGrades = auto ? LoadNav(profile, "grades") : "";
            DateTime captureDeadline = DateTime.UtcNow.AddSeconds(CaptureTimeoutSeconds);
            Func<bool> allDone = delegate {
                return (!(autoExams.Length > 0) || captured)
                    && (!(autoTimetable.Length > 0) || capturedTimetable)
                    && (!(autoGrades.Length > 0) || capturedGrades);
            };
            window.Controls.Add(browser);
            window.Controls.Add(status);
            timeout.Tick += delegate { timeout.Stop(); window.Close(); };
            poll.Tick += async delegate {
                if (!capture) { poll.Stop(); return; }
                if (allDone()) { poll.Stop(); return; }
                if (DateTime.UtcNow > captureDeadline)
                {
                    poll.Stop();
                    status.Text = "未检测到完整数据；可关闭窗口后重试。";
                    return;
                }
                try
                {
                    var current = browser.CoreWebView2;
                    if (current == null) return;
                    Uri here;
                    if (!Uri.TryCreate(current.Source, UriKind.Absolute, out here)) return;
                    if (here.IdnHost == "jiaowu.cqmu.edu.cn")
                    {
                        string pendingNav = !captured ? autoExams
                            : (!capturedTimetable ? autoTimetable : autoGrades);
                        int clickStep = !captured ? examClickStep
                            : (!capturedTimetable ? timetableClickStep : gradesClickStep);
                        string[] clickChain = pendingNav.StartsWith("click:")
                            ? pendingNav.Substring(6).Split('>')
                            : new string[0];
                        if (auto && clickChain.Length > clickStep
                            && DateTime.UtcNow >= clickRetryAt && clickAttempts < 10)
                        {
                            clickAttempts++;
                            clickRetryAt = DateTime.UtcNow.AddSeconds(6);
                            string label = clickChain[clickStep].Trim();
                            string clicked = await current.ExecuteScriptAsync(ReplayScript(label));
                            Trace("replay click[" + clickStep + "] '" + label + "' -> " + clicked);
                            bool ok = clicked != null
                                && (clicked.Contains("CLICKED") || clicked.Contains("RADIO:"));
                            if (ok)
                            {
                                if (!captured) examClickStep++;
                                else if (!capturedTimetable) timetableClickStep++;
                                else gradesClickStep++;
                                status.Text = "已自动打开：" + label;
                                return;
                            }
                        }
                        if (!captured) await current.ExecuteScriptAsync(ExtractExamsScript);
                        if (!capturedTimetable) await current.ExecuteScriptAsync(ExtractTimetableScript);
                        if (!capturedGrades) await current.ExecuteScriptAsync(ExtractGradesScript);
                        if (auto && captured && !capturedTimetable && !diagnoseDone
                            && DateTime.UtcNow >= diagnoseAt)
                        {
                            diagnoseDone = true;
                            Trace("diagnose " + await current.ExecuteScriptAsync(DiagnoseScript));
                        }
                        return;
                    }
                    // 自动模式：落在门户/登录页说明会话失效；登录完成后按记录的地址继续。
                    if (!auto || autoAttempts >= 3 || DateTime.UtcNow < autoRetryAt) return;
                    bool onLoginPage = (here.IdnHost == "cas.cqmu.edu.cn")
                        || here.AbsolutePath.ToLowerInvariant().Contains("login");
                    if (onLoginPage) return;
                    string target = !captured && autoExams.Length > 0 ? autoExams
                        : (!capturedTimetable && autoTimetable.Length > 0 ? autoTimetable : autoGrades);
                    if (target.Length == 0 || !IsUrlNav(target)) return;
                    autoAttempts++;
                    autoRetryAt = DateTime.UtcNow.AddSeconds(20);
                    status.Text = "已登录，自动前往：" + new Uri(target).AbsolutePath;
                    current.Navigate(target);
                }
                catch { }
            };
            window.FormClosed += delegate { Trace("window closed"); };
            window.Shown += async delegate {
                try {
                    if (smoke) timeout.Start();
                    Trace("start profile=" + (profile.Length == 0 ? "default" : profile)
                        + " mode=" + (auto ? "auto" : capture ? "capture" : "manual"));
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
                        Trace((request.Cancel ? "blocked " : "navigate ") + request.Uri);
                        status.Text = request.Cancel ? Blocked(request.Uri) : new Uri(request.Uri).GetLeftPart(UriPartial.Authority);
                    };
                    core.FrameNavigationStarting += (sender, request) => { request.Cancel = !Allowed(request.Uri); };
                    core.NavigationCompleted += async (sender, completedArgs) => {
                        try
                        {
                            Uri done;
                            if (!Uri.TryCreate(core.Source, UriKind.Absolute, out done)) return;
                            if (done.IdnHost != "jiaowu.cqmu.edu.cn") return;
                            await core.ExecuteScriptAsync(ClickRecorderScript);
                        }
                        catch { }
                    };
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
                                bool isGrades = message.StartsWith("GRADES\t", StringComparison.Ordinal);
                                if (!isExams && !isTimetable && !isGrades) return;
                                Uri origin;
                                if (!Uri.TryCreate(core.Source, UriKind.Absolute, out origin) ||
                                    origin.IdnHost != "jiaowu.cqmu.edu.cn") return;
                                string[] parts = message.Split('\t');
                                int count;
                                if (parts.Length < 3 || !int.TryParse(parts[1], out count) ||
                                    count <= 0 || count > CaptureMaxRows) return;
                                int width = isTimetable ? 3 : 4;
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
                                string clicked = parts.Length > count + 2 ? (parts[count + 2] ?? "").Trim() : "";
                                string kindName = isExams ? "exams" : (isTimetable ? "timetable" : "grades");
                                Trace("captured " + kindName + " rows=" + count + " click=" + clicked);
                                // 导航配置只做首次引导，已存在则不被覆盖（课表需要两步链路）。
                                string lastClick = clicked.Contains(">")
                                    ? clicked.Substring(clicked.LastIndexOf('>') + 1).Trim()
                                    : clicked.Trim();
                                if (isExams)
                                {
                                    WriteSnapshot(SnapshotName("exams", profile),
                                        BuildSnapshotJson("https://jiaowu.cqmu.edu.cn:8080", profile, rows));
                                    if (!NavExists(profile, "exams"))
                                        SaveNav(profile, "exams",
                                            lastClick.Length > 0 ? "click:" + lastClick : core.Source);
                                    captured = true;
                                    examCount = count;
                                    diagnoseAt = DateTime.UtcNow.AddSeconds(20);
                                }
                                else if (isTimetable)
                                {
                                    WriteSnapshot(SnapshotName("timetable", profile),
                                        BuildTimetableJson("https://jiaowu.cqmu.edu.cn:8080", profile, rows));
                                    if (!NavExists(profile, "timetable"))
                                        SaveNav(profile, "timetable",
                                            lastClick.Length > 0 ? "click:" + lastClick : core.Source);
                                    capturedTimetable = true;
                                    timetableCount = count;
                                }
                                else
                                {
                                    WriteSnapshot(SnapshotName("grades", profile),
                                        BuildGradesJson("https://jiaowu.cqmu.edu.cn:8080", profile, rows));
                                    if (!NavExists(profile, "grades"))
                                        SaveNav(profile, "grades",
                                            lastClick.Length > 0 ? "click:" + lastClick : core.Source);
                                    capturedGrades = true;
                                    gradeCount = count;
                                }
                                status.Text = "已保存：考试 " + examCount + " 条、课表 " + timetableCount
                                    + " 条、成绩 " + gradeCount + " 条。";
                                if (allDone())
                                {
                                    poll.Stop();
                                    if (auto) { status.Text += "同步完成，窗口即将关闭。"; CloseLater(window, 1500); }
                                    else status.Text += "可继续切换到其他查询页，或关闭窗口。";
                                }
                            }
                            catch (Exception)
                            {
                                status.Text = "捕获失败；可留在考试查询页等待自动重试。";
                            }
                        };
                        poll.Start();
                        if (auto && autoExams.Length == 0)
                            status.Text = "首次自动同步：请登录并打开「考试查询」；之后会自动完成。";
                    }
                    if (smoke) { result = 0; window.Close(); return; }
                    if (auto)
                    {
                        string first = IsUrlNav(autoExams) ? autoExams : EamsHome;
                        status.Text = "自动同步中…";
                        Trace("auto goto " + first);
                        core.Navigate(first);
                    }
                    else
                    {
                        Trace("open portal (no saved nav)");
                        core.Navigate(Portal);
                    }
                    result = 0;
                } catch (Exception error) {
                    Trace("startup error " + error);
                    status.Text = "启动失败：" + error.GetType().Name;
                    if (smoke) window.Close();
                }
            };
            Application.Run(window);
        }
        return result;
    }
}
