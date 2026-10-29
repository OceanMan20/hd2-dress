// Send the Helldivers 2 window (gamescope; no window class, only a title) to the portrait screen DP-1.
var TARGET = "DP-1";
function target() {
    var s = workspace.screens;
    for (var i = 0; i < s.length; i++) if (s[i].name === TARGET) return s[i];
    return null;
}
function place(w) {
    if (!w || !w.caption || w.caption.indexOf("HELLDIVERS") < 0) return;
    var out = target();
    if (out && w.output !== out) workspace.sendClientToScreen(w, out);
}
function watch(w) {
    place(w);
    w.captionChanged.connect(function () { place(w); });
    w.fullScreenChanged.connect(function () { place(w); });
}
var list = workspace.windowList();
for (var i = 0; i < list.length; i++) watch(list[i]);
workspace.windowAdded.connect(watch);
