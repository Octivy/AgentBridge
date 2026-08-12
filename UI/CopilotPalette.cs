using System;
using Autodesk.AutoCAD.Windows;
using AgentBridge.Core;

namespace AgentBridge.UI
{
    public static class CopilotPalette
    {
        private static readonly System.Drawing.Size DefaultPaletteSize = new System.Drawing.Size(420, 760);
        private static PaletteSet _paletteSet;
        private static ChatPanel _chatPanel;

        public static void Show()
        {
            try
            {
                if (_paletteSet == null)
                {
                    CreatePalette();
                }

                if (_paletteSet.Size.Width < 380 || _paletteSet.Size.Height < 620)
                {
                    _paletteSet.Size = DefaultPaletteSize;
                }

                _paletteSet.Dock = DockSides.Right;
                _paletteSet.Visible = true;
                Logger.Info("Copilot palette shown. Size=" + _paletteSet.Size.Width + "x" + _paletteSet.Size.Height + ", Dock=" + _paletteSet.Dock);
                if (_chatPanel != null)
                {
                    _chatPanel.FocusInput();
                }
            }
            catch (Exception ex)
            {
                Logger.Error("Failed to show Copilot palette: " + ex);
                Dispose();
                throw;
            }
        }

        public static void AppendMessage(string role, string content)
        {
            if (_chatPanel == null)
            {
                return;
            }

            _chatPanel.AddMessage(role, content);
        }

        public static void Hide()
        {
            if (_paletteSet == null)
            {
                return;
            }

            _paletteSet.Visible = false;
        }

        public static void ToggleExpandedLayout()
        {
            if (_paletteSet == null)
            {
                return;
            }

            System.Drawing.Size currentSize = _paletteSet.Size;
            int targetWidth = currentSize.Width >= 520 ? 400 : 560;
            _paletteSet.Size = new System.Drawing.Size(targetWidth, currentSize.Height);
        }

        public static void Dispose()
        {
            if (_paletteSet != null)
            {
                _paletteSet.Close();
                _paletteSet = null;
            }

            _chatPanel = null;
        }

        private static void CreatePalette()
        {
            PaletteSet paletteSet = new PaletteSet("AgentBridge", new Guid("7A8D3E2F-1B4C-4D5E-9F6A-0C8B7D2E1A3F"))
            {
                Style = PaletteSetStyles.ShowAutoHideButton | PaletteSetStyles.ShowCloseButton | PaletteSetStyles.Snappable,
                MinimumSize = new System.Drawing.Size(400, 620),
                Size = DefaultPaletteSize,
                KeepFocus = true,
                DockEnabled = DockSides.Left | DockSides.Right,
                Dock = DockSides.Right
            };

            ChatPanel chatPanel = new ChatPanel();
            System.Windows.Forms.Integration.ElementHost host = new System.Windows.Forms.Integration.ElementHost
            {
                AutoSize = false,
                Dock = System.Windows.Forms.DockStyle.Fill,
                Child = chatPanel
            };

            paletteSet.Add("Chat", host);
            _paletteSet = paletteSet;
            _chatPanel = chatPanel;
            Logger.Info("Copilot palette created. Size=" + _paletteSet.Size.Width + "x" + _paletteSet.Size.Height + ", Dock=" + _paletteSet.Dock);
            _paletteSet.Visible = true;
            _chatPanel.FocusInput();
        }
    }
}