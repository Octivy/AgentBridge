using System.Windows.Media;

namespace AgentBridge.UI
{
    internal static class CopilotUiTokens
    {
        internal const string Surface = "#1E1E1E";
        internal const string SurfaceRaised = "#202220";
        internal const string Border = "#3A3D41";
        internal const string BorderSoft = "#323438";
        internal const string TextPrimary = "#F3F6F8";
        internal const string TextSecondary = "#C8CDD4";
        internal const string TextMuted = "#8F969E";
        internal const string Success = "#5BD68A";
        internal const string Warning = "#D7BA7D";
        internal const string Danger = "#F48771";
        internal const string BadgeBackground = "#2A2D2A";
        internal const string BadgeBorder = "#454A45";

        internal static SolidColorBrush Brush(string color)
        {
            return new SolidColorBrush((Color)ColorConverter.ConvertFromString(color));
        }
    }
}
