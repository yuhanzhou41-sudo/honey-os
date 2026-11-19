using System;
using System.IO;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal static class CampusHost
{
    private const string Portal = "https://my.cqmu.edu.cn/";

    private static bool Allowed(string target)
    {
        Uri uri;
        return Uri.TryCreate(target, UriKind.Absolute, out uri) && (uri.Scheme == "https" || uri.Scheme == "http") &&
            uri.IsDefaultPort && uri.UserInfo.Length == 0 && (uri.IdnHost == "my.cqmu.edu.cn" ||
            uri.IdnHost == "cas.cqmu.edu.cn" || uri.IdnHost == "jiaowu.cqmu.edu.cn");
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

    [STAThread]
    private static int Main(string[] args)
    {
        bool smoke = args.Length == 1 && args[0] == "--smoke";
        if (args.Length != 0 && !smoke) return 2;
        Application.EnableVisualStyles();
        int result = 1;
        using (var window = new Form { Text = "HoneyOS · 校园连接验证", Width = 1000, Height = 720 })
        using (var browser = new WebView2 { Dock = DockStyle.Fill })
        using (var status = new Label { Dock = DockStyle.Top, Height = 32, Text = "正在启动独立校园窗口…" })
        using (var timeout = new Timer { Interval = 30000 })
        {
            window.Controls.Add(browser);
            window.Controls.Add(status);
            timeout.Tick += delegate { timeout.Stop(); window.Close(); };
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
                    core.Settings.IsWebMessageEnabled = false;
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
