using System;
using System.Collections.ObjectModel;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Globalization;
using System.Linq;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using AgentBridge.Core;
using AgentBridge.Engine;
using AgentBridge.LLM;
using Microsoft.Win32;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace AgentBridge.UI
{
    public partial class ChatPanel : UserControl
    {
        private const string ConnectionModeService = "service";
        private const string ConnectionModeStandard = "standard";
        private const string LegacyConnectionModeDirect = "direct";
        private const string AgentApprovalAnnotate = "annotate";
        private const string AgentApprovalExecute = "execute";
        private const string AgentApprovalFull = "full";
        private const string ModelManagerOption = "__manage_models__";
        private const string ProviderOpenAi = "openai";
        private const string ProviderDeepSeek = "deepseek";
        private const string ProviderMiniMax = "minimax";
        private const string ProviderCadCopilot = "cadcopilot";
        private const string ProviderAnthropic = "anthropic";
        private const string ProviderOpenAiCompatible = "openai_compatible";
        private const string ProviderOllama = "ollama";
        private const string ProviderEnterprisePrivate = "enterprise_private";
        private const string DefaultServiceModel = "MiniMax-M2.7";
        private const string DefaultOfficialModel = "AgentBridge-Default";
        private const string DefaultMiniMaxModel = "MiniMax-M2.7";
        private const string DefaultOpenAiModel = "gpt-5.5";
        private const string DefaultDeepSeekModel = "deepseek-v4";
        private const string DefaultAnthropicModel = "claude-sonnet-4-20250514";
        private const string DefaultOllamaModel = "qwen3:8b";
        private const string DefaultCompatibleModel = "model-name";
        private const string DefaultEnterpriseModel = "enterprise-default";
        private const string DefaultOpenAiBaseUrl = "https://api.openai.com/v1";
        private const string DefaultDeepSeekBaseUrl = "https://api.deepseek.com/v1";
        private const string DefaultMiniMaxBaseUrl = "https://api.minimaxi.com/v1";
        private const string DefaultAnthropicBaseUrl = "https://api.anthropic.com/v1";
        private const string DefaultOllamaBaseUrl = "http://127.0.0.1:11434/v1";
        private const string PluginVersion = "0.9.0.622";
        private const int MaxPinnedTools = 32;

        private static readonly string[] OpenAiModelOptions = { DefaultOpenAiModel, "gpt-5.4", "gpt-5" };
        private static readonly string[] DeepSeekModelOptions = { DefaultDeepSeekModel };
        private static readonly string[] MiniMaxModelOptions = { DefaultMiniMaxModel };
        private static readonly string[] CadCopilotModelOptions = { DefaultOfficialModel, DefaultMiniMaxModel };
        private static readonly string[] AnthropicModelOptions = { DefaultAnthropicModel };
        private static readonly string[] OllamaModelOptions = { DefaultOllamaModel };
        private static readonly string[] CompatibleModelOptions = { DefaultCompatibleModel };
        private static readonly string[] EnterpriseModelOptions = { DefaultEnterpriseModel };
        private static readonly ToolDefinition[] AllTools =
        {
            new ToolDefinition(
                "recognize_drawing",
                "识",
                "图纸快照分析",
                "读取当前图纸的图层、实体、块、文字、尺寸和未知代理对象。",
                "读取当前图纸并给出结构化摘要，明确列出未知或不支持的对象，不要修改图纸。",
                true),
            new ToolDefinition(
                "recognize_functional_objects",
                "辨",
                "功能对象识别",
                "将图层线、普通块、动态块和可读取对象识别为墙、门、窗或未知对象。",
                "识别当前图纸中的功能对象，说明每个结论的证据、置信度和支持状态，不要修改图纸。",
                true),
            new ToolDefinition(
                "outer_outline",
                "廓",
                "外围轮廓",
                "提取最外围闭合轮廓并计算面积；需要落图时先预览再确认。",
                "提取当前平面的最外围闭合轮廓并计算面积。先返回预览；只有我确认后才绘制闭合多段线。",
                true),
            new ToolDefinition(
                "layer_standard",
                "层",
                "图层统一",
                "给出保守的图层映射建议；迁移实体前必须确认。",
                "分析当前图层并给出统一映射建议，未知图层保持不变。先预览；只有我确认后才迁移实体。",
                true)
        };
        private sealed class ToolDefinition
        {
            public ToolDefinition(string key, string glyph, string name, string description, string prompt, bool requiresAgent)
            {
                Key = key;
                Glyph = glyph;
                Name = name;
                Description = description;
                Prompt = prompt;
                RequiresAgent = requiresAgent;
            }

            public string Key { get; }
            public string Glyph { get; }
            public string Name { get; }
            public string Description { get; }
            public string Prompt { get; }
            public bool RequiresAgent { get; }
        }

        private sealed class StepTrackerHandle
        {
            public Border Container { get; set; }
            public StackPanel BodyPanel { get; set; }
            public TextBlock CollapseGlyphText { get; set; }
            public TextBlock ToggleGlyphText { get; set; }
            public TextBlock TitleText { get; set; }
            public List<TextBlock> MarkerTexts { get; set; }
            public List<TextBlock> ItemTexts { get; set; }
            public bool IsCollapsed { get; set; }
        }

        private sealed class MessageBubbleHandle
        {
            public Border Shell { get; set; }
            public StackPanel MessageStack { get; set; }
            public Border Bubble { get; set; }
            public TextBox ContentText { get; set; }
            public bool IsThinking { get; set; }
        }

        private sealed class PlannerTaskActionContext
        {
            public string Action { get; set; }
            public string TaskId { get; set; }
            public string Value { get; set; }
        }

        private sealed class DirectModelProfile
        {
            public string ModelName { get; set; }
            public string ApiKey { get; set; }
            public string Provider { get; set; }
            public string ApiBaseUrl { get; set; }
        }

        private sealed class ServiceModelProfile
        {
            public string ModelName { get; set; }
        }

        private sealed class ConversationSession
        {
            public string Id { get; set; }
            public string Title { get; set; }
            public List<UIElement> MessageChildren { get; set; }
        }

        private sealed class ProviderDefinition
        {
            public string Key { get; set; }
            public string DisplayName { get; set; }
            public string DefaultBaseUrl { get; set; }
            public string[] ModelOptions { get; set; }
        }

        private static readonly ProviderDefinition[] SupportedProviders =
        {
            new ProviderDefinition
            {
                Key = ProviderCadCopilot,
                DisplayName = "AgentBridge",
                DefaultBaseUrl = string.Empty,
                ModelOptions = CadCopilotModelOptions
            },
            new ProviderDefinition
            {
                Key = ProviderMiniMax,
                DisplayName = "MiniMax",
                DefaultBaseUrl = DefaultMiniMaxBaseUrl,
                ModelOptions = MiniMaxModelOptions
            },
            new ProviderDefinition
            {
                Key = ProviderOpenAi,
                DisplayName = "OpenAI",
                DefaultBaseUrl = DefaultOpenAiBaseUrl,
                ModelOptions = OpenAiModelOptions
            },
            new ProviderDefinition
            {
                Key = ProviderDeepSeek,
                DisplayName = "DeepSeek",
                DefaultBaseUrl = DefaultDeepSeekBaseUrl,
                ModelOptions = DeepSeekModelOptions
            },
            new ProviderDefinition
            {
                Key = ProviderAnthropic,
                DisplayName = "Anthropic / Claude",
                DefaultBaseUrl = DefaultAnthropicBaseUrl,
                ModelOptions = AnthropicModelOptions
            },
            new ProviderDefinition
            {
                Key = ProviderOpenAiCompatible,
                DisplayName = "OpenAI Compatible",
                DefaultBaseUrl = string.Empty,
                ModelOptions = CompatibleModelOptions
            },
            new ProviderDefinition
            {
                Key = ProviderOllama,
                DisplayName = "Ollama / 本地模型",
                DefaultBaseUrl = DefaultOllamaBaseUrl,
                ModelOptions = OllamaModelOptions
            },
            new ProviderDefinition
            {
                Key = ProviderEnterprisePrivate,
                DisplayName = "企业内网模型",
                DefaultBaseUrl = string.Empty,
                ModelOptions = EnterpriseModelOptions
            }
        };

        private ClaudeClient _llmClient;
        private bool _isBusy;
        private bool _isLoadingSettings;
        private byte[] _pendingImage;
        private string _pendingAttachmentName;
        private string _pendingAttachmentKind;
        private string _pendingAttachmentText;
        private string _pendingAttachmentMeta;
        private string _currentStatus = "就绪";
        private bool _isInputFocused;
        private readonly ObservableCollection<ToolDefinition> _pinnedTools = new ObservableCollection<ToolDefinition>();
        private Point _dragStartPoint;
        private string _draggingToolKey;
        private bool _draggingFromPinnedBar;
        private readonly DispatcherTimer _thinkingIndicatorTimer;
        private MessageBubbleHandle _activeThinkingBubble;
        private int _thinkingFrame;
        private string _taskPanelFilter = "all";
        private string _taskPanelSelectedTaskId = string.Empty;
        private DrawCommandResponse _lastReviewSnapshot;
        private List<DirectModelProfile> _directProfiles = new List<DirectModelProfile>();
        private List<ServiceModelProfile> _serviceProfiles = new List<ServiceModelProfile>();
        private bool _isUpdatingProfileSelectors;
        private string _profileValidatedProvider;
        private string _profileValidatedModel;
        private string _profileValidatedApiKey;
        private readonly List<ConversationSession> _conversationSessions = new List<ConversationSession>();
        private string _activeConversationId = string.Empty;
        private int _conversationSequence = 1;
        private readonly Dictionary<string, SkillDefinitionResponse> _skillDefinitionCache = new Dictionary<string, SkillDefinitionResponse>(StringComparer.OrdinalIgnoreCase);
        private string _pendingWriteConfirmationTaskId = string.Empty;
        public ChatPanel()
        {
            InitializeComponent();
            UpdateConfigEditorState();
            _thinkingIndicatorTimer = new DispatcherTimer
            {
                Interval = TimeSpan.FromMilliseconds(420)
            };
            _thinkingIndicatorTimer.Tick += ThinkingIndicatorTimer_Tick;
            InitializeToolbar();
            ReloadClient();
            LoadSettingsIntoView();
            DataObject.AddPastingHandler(InputBox, OnPaste);
            Loaded += ChatPanel_Loaded;
            SizeChanged += ChatPanel_SizeChanged;
            MessageScroller.SizeChanged += MessageScroller_SizeChanged;
            InputBox.PreviewMouseLeftButtonDown += EditableTextBox_PreviewMouseLeftButtonDown;
            InputBox.PreviewKeyDown += EditableTextBox_PreviewKeyDown;
            InputBox.SelectionBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#4A8DDE"));
            InputBox.SelectionOpacity = 0.35;
            InputBox.ContextMenu = CreateEditableTextContextMenu(InputBox);
            UpdateConnectionModeButtonVisual();
            UpdateInputPlaceholder();
            SetStatus("就绪");
            AddWelcomeMessage();
            InitializeConversationTabs();
        }

        public void AddMessage(string role, string content)
        {
            Dispatcher.Invoke(() =>
            {
                AppendMessageBubble(role, content);
            });
        }

        private void AddPlannerActionPanel(DrawCommandResponse response)
        {
            bool hasParameterRequest = IsPlannerAwaitingSkillParameters(response);
            bool hasPreview = HasPlannerPreview(response);
            if (!hasParameterRequest && !hasPreview)
            {
                return;
            }

            if (hasPreview)
            {
                RememberReviewSnapshot(response);
                SetPendingWriteConfirmation(response);
            }
            else
            {
                ClearPendingWriteConfirmation();
            }

            Dispatcher.Invoke(() =>
            {
                UIElement panel = hasParameterRequest
                    ? BuildParameterRequestPanel(response, new Thickness(0))
                    : BuildPlannerPreviewCard(response, new Thickness(0));
                AddAssistantPanelToMessageList(panel);
            });
        }

        private void SetPendingWriteConfirmation(DrawCommandResponse response)
        {
            _pendingWriteConfirmationTaskId = IsPlannerAwaitingWriteConfirmation(response) ? GetPlannerTaskId(response) : string.Empty;
            RefreshSendButtonIntent();
        }

        private void ClearPendingWriteConfirmation()
        {
            _pendingWriteConfirmationTaskId = string.Empty;
            RefreshSendButtonIntent();
        }

        private void RefreshSendButtonIntent()
        {
            if (SendButton == null)
            {
                return;
            }

            bool awaitingPermission = !string.IsNullOrWhiteSpace(_pendingWriteConfirmationTaskId);
            SendButton.Content = awaitingPermission ? "允许" : "发送";
            SendButton.ToolTip = awaitingPermission
                ? "允许当前智能体任务写入图纸；如果需要调整，请在输入框中说明要求后再发送。"
                : "发送";
        }

        private void AddPlannerProcessPanel(DrawCommandResponse response)
        {
            if (!HasPlannerProcessPayload(response))
            {
                return;
            }

            Dispatcher.Invoke(() =>
            {
                AddAssistantPanelToMessageList(BuildPlannerProcessCard(response, new Thickness(0)));
            });
        }

        private void AddAssistantPanelToMessageList(UIElement panel)
        {
            FrameworkElement frameworkElement = panel as FrameworkElement;
            if (frameworkElement != null)
            {
                frameworkElement.HorizontalAlignment = HorizontalAlignment.Left;
                frameworkElement.MaxWidth = CalculateMessageBubbleMaxWidth("assistant");
            }

            StackPanel messageStack = new StackPanel
            {
                HorizontalAlignment = HorizontalAlignment.Left,
                Margin = new Thickness(0, 0, 72, 0)
            };
            messageStack.Children.Add(panel);
            Border shell = new Border
            {
                Child = messageStack,
                Margin = new Thickness(0, 0, 0, 10)
            };

            MessageList.Children.Add(shell);
            RefreshMessageBubbleWidths();
            MessageScroller.ScrollToEnd();
        }

        private async void Send_Click(object sender, RoutedEventArgs e)
        {
            if (!string.IsNullOrWhiteSpace(_pendingWriteConfirmationTaskId) && string.IsNullOrWhiteSpace(InputBox.Text))
            {
                await ConfirmPlannerTaskAsync(_pendingWriteConfirmationTaskId);
                return;
            }

            await SendMessage();
        }

        private async Task SendMessage()
        {
            string text = (InputBox.Text ?? string.Empty).Trim();
            if ((text.Length == 0 && _pendingImage == null && string.IsNullOrWhiteSpace(_pendingAttachmentText)) || _isBusy)
            {
                return;
            }

            _isBusy = true;
            SendButton.IsEnabled = false;
            AttachButton.IsEnabled = false;

            byte[] imageData = _pendingImage;
            string attachmentName = _pendingAttachmentName;
            string attachmentKind = _pendingAttachmentKind;
            string attachmentText = _pendingAttachmentText;
            string attachmentMeta = _pendingAttachmentMeta;
            ClearPendingAttachment();

            AddMessage("user", BuildUserPreviewText(text, attachmentKind, attachmentName));
            UpdateActiveConversationTitleFromPrompt(text, attachmentName);
            InputBox.Text = string.Empty;
            UpdateInputPlaceholder();
            MessageBubbleHandle pendingAssistant = AddPendingAssistantBubble();
            string requestText = DrawingContextService.BuildAugmentedPrompt(BuildRequestText(text, attachmentKind, attachmentName, attachmentText, attachmentMeta));
            string finalStatus = "就绪";

            try
            {
                if (!UseServiceMode())
                {
                    ClearTaskStepper();
                    LlmTextResponse response = await _llmClient.ChatWithMetadata(requestText, imageData);
                    UpdateMessageBubble(pendingAssistant, "assistant", response != null ? response.ReplyText : string.Empty);
                }
                else
                {
                    List<string> taskSteps = await BuildTaskPlanAsync(text, attachmentKind, attachmentName, attachmentText);
                    StepTrackerHandle tracker = AddTaskStepper(taskSteps);

                    UpdateTaskStepper(tracker, 1);
                    DrawCommandResponse response = await _llmClient.GetDrawCommands(requestText, imageData);
                    DrawCommandResponse plannerSnapshot = await TryRefreshPlannerTaskSnapshotAsync(response);
                    tracker = SyncPlannerTaskStepper(tracker, plannerSnapshot);
                    if (IsLegacyServiceCommandFallback(response))
                    {
                        UpdateTaskStepper(tracker, 2);
                        UpdateMessageBubble(pendingAssistant, "assistant", string.IsNullOrWhiteSpace(response.ReplyText) ? "收到，当前服务返回了兼容指令，我将按旧路径执行绘图操作。" : response.ReplyText);
                        ReportLegacyFallbackNotice();

                        MainThreadDispatcher.Enqueue(() =>
                        {
                            int count = CommandExecutor.Execute(response.Commands);
                            UpdateTaskStepper(tracker, tracker.ItemTexts.Count);
                            AddMessage("system", "执行完成，绘制了 " + count + " 个图元。");
                            ClearTaskStepper();
                        });
                    }
                    else if (HasIncompatibleLegacyCommands(response))
                    {
                        finalStatus = "智能体响应契约不兼容";
                        UpdateMessageBubble(pendingAssistant, "error", BuildIncompatibleLegacyCommandMessage(response));
                        AddMessage("system", "当前响应包含 legacy commands，但没有显式 legacy_fallback_used 标记。该响应已被拒绝执行，请同步更新 copilot backend。");
                        ClearTaskStepper();
                    }
                    else
                    {
                        string reply = BuildPlannerReplyFallback(plannerSnapshot);
                        UpdateMessageBubble(pendingAssistant, "assistant", reply);
                        AddPlannerProcessPanel(plannerSnapshot);
                        List<PlannerExecutionEventResponse> executionEvents = GetPlannerExecutionEvents(plannerSnapshot);
                        if (executionEvents.Count > 0)
                        {
                            AddMessage("system", BuildPlannerExecutionEventSummary(executionEvents));
                        }
                        else
                        {
                            List<string> executedTools = GetPlannerExecutedTools(plannerSnapshot);
                            if (executedTools.Count > 0)
                            {
                                AddMessage("system", "智能体已通过 Planner 执行工具: " + string.Join("、", executedTools) + "。");
                            }
                        }

                        if (IsPlannerWaitingUser(plannerSnapshot))
                        {
                            int progressCount = ResolvePlannerProgressCount(tracker, plannerSnapshot);
                            UpdateTaskStepper(tracker, progressCount);
                            if (IsPlannerAwaitingWriteConfirmation(plannerSnapshot))
                            {
                                tracker.TitleText.Text = "等待应用到图纸(" + progressCount + "/" + tracker.ItemTexts.Count + ")";
                                finalStatus = "等待应用到图纸";
                                AddPlannerActionPanel(plannerSnapshot);
                                AddMessage("system", BuildPlannerFollowUpHint(plannerSnapshot));
                                return;
                            }
                            tracker.TitleText.Text = "待补充信息(" + progressCount + "/" + tracker.ItemTexts.Count + ")";
                            finalStatus = "等待补充信息";
                            AddPlannerActionPanel(plannerSnapshot);
                            AddMessage("system", BuildPlannerFollowUpHint(plannerSnapshot));
                        }
                        else if (IsPlannerCompleted(plannerSnapshot))
                        {
                            UpdateTaskStepper(tracker, tracker.ItemTexts.Count);
                            finalStatus = "智能体任务完成";
                            AddMessage("system", BuildPlannerCompletionHint(plannerSnapshot));
                            ClearTaskStepper();
                        }
                        else if (IsPlannerFailed(plannerSnapshot))
                        {
                            UpdateTaskStepper(tracker, Math.Max(1, ResolvePlannerProgressCount(tracker, plannerSnapshot)));
                            finalStatus = "智能体任务失败";
                            AddMessage("system", BuildPlannerFailureHint(plannerSnapshot));
                            ClearTaskStepper();
                        }
                        else
                        {
                            UpdateTaskStepper(tracker, tracker.ItemTexts.Count);
                            ClearTaskStepper();
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                ClearTaskStepper();
                UpdateMessageBubble(pendingAssistant, "error", ex.Message);
                finalStatus = "发送失败";
                Logger.Error("Chat panel send failed: " + ex);
            }
            finally
            {
                _isBusy = false;
                SendButton.IsEnabled = true;
                AttachButton.IsEnabled = true;
                SetStatus(finalStatus);
                FocusInputBox(true);
            }
        }

        private void HeaderNewConversation_Click(object sender, RoutedEventArgs e)
        {
            NewConversation_Click(sender, e);
        }

        private void CloseWorkSurfaceDrawers(FrameworkElement except = null)
        {
            CollapseDrawerUnless(ConfigDrawer, except);
            CollapseDrawerUnless(TaskCenterDrawer, except);
            CollapseDrawerUnless(DiagnosticsDrawer, except);
            CollapseDrawerUnless(ReviewDrawer, except);
            CollapseDrawerUnless(ContextDrawer, except);
        }

        private static void CollapseDrawerUnless(FrameworkElement drawer, FrameworkElement except)
        {
            if (drawer != null && !ReferenceEquals(drawer, except))
            {
                drawer.Visibility = Visibility.Collapsed;
            }
        }

        private void HeaderSettings_Click(object sender, RoutedEventArgs e)
        {
            OpenSettingsWindow("通用");
        }

        private void OpenSettingsDrawer(string status)
        {
            OpenSettingsWindow(status);
        }

        private void OpenSettingsWindow(string section)
        {
            Window window = new Window
            {
                Title = "AgentBridge 设置",
                Width = 980,
                Height = 720,
                MinWidth = 760,
                MinHeight = 560,
                WindowStartupLocation = WindowStartupLocation.CenterScreen,
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#171817")),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3")),
                Content = BuildSettingsWindowContent(section)
            };
            window.Show();
            SetStatus("设置");
        }

        private UIElement BuildSettingsWindowContent(string section)
        {
            Grid shell = new Grid { Margin = new Thickness(0) };
            shell.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(190) });
            shell.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

            ListBox navigation = new ListBox
            {
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#171817")),
                BorderThickness = new Thickness(0),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#C8CDD4")),
                Padding = new Thickness(18, 20, 10, 20)
            };
            string[] sections = { "通用", "模型", "技能库", "帮助文档", "问题反馈" };
            for (int i = 0; i < sections.Length; i++)
            {
                navigation.Items.Add(sections[i]);
            }

            ContentControl content = new ContentControl
            {
                Margin = new Thickness(24, 22, 28, 22)
            };
            navigation.SelectionChanged += (sender, args) =>
            {
                string selected = navigation.SelectedItem as string ?? "通用";
                content.Content = BuildSettingsSection(selected);
            };

            string initial = ResolveSettingsSection(section);
            navigation.SelectedItem = initial;
            content.Content = BuildSettingsSection(initial);

            Grid.SetColumn(navigation, 0);
            Grid.SetColumn(content, 1);
            shell.Children.Add(navigation);
            shell.Children.Add(content);
            return shell;
        }

        private static string ResolveSettingsSection(string section)
        {
            string value = (section ?? string.Empty).Trim();
            if (value.Contains("模型"))
            {
                return "模型";
            }

            if (value.Contains("技能"))
            {
                return "技能库";
            }

            if (value.Contains("帮助"))
            {
                return "帮助文档";
            }

            if (value.Contains("反馈"))
            {
                return "问题反馈";
            }

            return "通用";
        }

        private UIElement BuildSettingsSection(string section)
        {
            if (section == "模型")
            {
                return BuildModelSettingsSection();
            }

            if (section == "技能库")
            {
                return BuildSkillsSettingsSection();
            }

            if (section == "帮助文档")
            {
                return BuildHelpSettingsSection();
            }

            if (section == "问题反馈")
            {
                return BuildFeedbackSettingsSection();
            }

            return BuildGeneralSettingsSection();
        }

        private UIElement BuildGeneralSettingsSection()
        {
            StackPanel panel = CreateSettingsPanel("通用");
            ComboBox languageBox = CreateSettingsCombo("简体中文", "English");
            panel.Children.Add(CreateSettingsRow("界面显示语言", "设置插件界面的显示语言。", languageBox));

            CheckBox notificationToggle = new CheckBox
            {
                IsChecked = string.Equals(Config.Get("CADCOPILOT_NOTIFICATIONS_ENABLED", "true"), "true", StringComparison.OrdinalIgnoreCase),
                VerticalAlignment = VerticalAlignment.Center,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3"))
            };
            notificationToggle.Checked += (sender, args) => Config.Set("CADCOPILOT_NOTIFICATIONS_ENABLED", "true");
            notificationToggle.Unchecked += (sender, args) => Config.Set("CADCOPILOT_NOTIFICATIONS_ENABLED", "false");
            panel.Children.Add(CreateSettingsRow("通知", "会话完成或需要操作时显示插件内通知。", notificationToggle));
            panel.Children.Add(CreateSettingsCard("连接器", "当前版本 v" + PluginVersion + "。当前只保留 CAD、MCP、Planner 与多模型连接能力。", null, null));
            return WrapSettingsScroll(panel);
        }

        private UIElement BuildModelSettingsSection()
        {
            StackPanel panel = CreateSettingsPanel("模型");
            Grid header = new Grid { Margin = new Thickness(0, 0, 0, 14) };
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            TextBlock description = new TextBlock
            {
                Text = "使用自有 API Key 管理自定义模型。  查看文档",
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#9DA5A0")),
                FontSize = 12
            };
            Button addButton = new Button
            {
                Content = "+ 添加",
                Style = (Style)FindResource("TopActionButtonStyle"),
                Padding = new Thickness(10, 4, 10, 4),
                BorderThickness = new Thickness(1),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#343831"))
            };
            addButton.Click += AddCustomModel_Click;
            Grid.SetColumn(addButton, 1);
            header.Children.Add(description);
            header.Children.Add(addButton);
            panel.Children.Add(header);

            LoadDirectProfiles();
            if (_directProfiles.Count == 0)
            {
                panel.Children.Add(CreateSettingsCard("暂无自定义模型", "点击添加模型开始使用。可接入平台后续参考 Qoder/Copilot 方式继续补充。", "添加", AddCustomModel_Click));
            }
            else
            {
                for (int i = 0; i < _directProfiles.Count; i++)
                {
                    DirectModelProfile profile = _directProfiles[i];
                    if (profile == null || string.IsNullOrWhiteSpace(profile.ModelName))
                    {
                        continue;
                    }

                    panel.Children.Add(CreateSettingsCard(profile.ModelName, GetProviderDisplayName(profile.Provider) + " · 自定义模型", "启用", (sender, args) =>
                    {
                        Config.Set("LLM_PROVIDER", profile.Provider);
                        Config.Set("OPENAI_API_BASE_URL", profile.ApiBaseUrl ?? string.Empty);
                        Config.Set("OPENAI_MODEL", profile.ModelName ?? string.Empty);
                        Config.Set("CADCOPILOT_MODEL", profile.ModelName ?? string.Empty);
                        Config.Set("OPENAI_API_KEY", profile.ApiKey ?? string.Empty);
                        LoadSettingsIntoView();
                        ReloadClient();
                        RefreshModelSelector();
                    }));
                }
            }
            return WrapSettingsScroll(panel);
        }

        private void AddCustomModel_Click(object sender, RoutedEventArgs e)
        {
            ShowAddModelDialog();
        }

        private void ShowAddModelDialog()
        {
            Window dialog = new Window
            {
                Title = "添加模型",
                Width = 680,
                Height = 560,
                WindowStartupLocation = WindowStartupLocation.CenterScreen,
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#242622")),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3"))
            };

            StackPanel panel = new StackPanel { Margin = new Thickness(26) };
            ComboBox providerBox = CreateSettingsCombo("MiniMax", "OpenAI", "Anthropic", "DeepSeek", "OpenAI Compatible", "Ollama", "企业内网模型");
            ComboBox typeBox = CreateSettingsCombo("OpenAI Compatible", "Anthropic Messages");
            TextBox modelBox = CreateSettingsTextBox("");
            PasswordBox apiKeyBox = new PasswordBox
            {
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#111210")),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3")),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#343831")),
                Padding = new Thickness(10, 7, 10, 7)
            };
            panel.Children.Add(CreateSettingsRow("提供商", "选择模型平台。", providerBox));
            panel.Children.Add(CreateSettingsRow("类型", "当前预留 Token plan 和 OpenAI Compatible。", typeBox));
            panel.Children.Add(CreateSettingsRow("模型", "填写模型名称。", modelBox));
            panel.Children.Add(CreateSettingsRow("API 密钥", "密钥只保存在本机配置中。", apiKeyBox));
            Button save = new Button
            {
                Content = "添加",
                Style = (Style)FindResource("PrimaryButtonStyle"),
                HorizontalAlignment = HorizontalAlignment.Right,
                Margin = new Thickness(0, 12, 0, 0)
            };
            save.Click += (sender, args) =>
            {
                string provider = NormalizeProviderName(GetComboSelectedText(providerBox));
                DirectModelProfile profile = new DirectModelProfile
                {
                    Provider = provider,
                    ModelName = (modelBox.Text ?? string.Empty).Trim(),
                    ApiKey = apiKeyBox.Password ?? string.Empty,
                    ApiBaseUrl = GetProviderDefaultBaseUrl(provider)
                };
                if (string.IsNullOrWhiteSpace(profile.ModelName) || string.IsNullOrWhiteSpace(profile.ApiKey))
                {
                    MessageBox.Show("请填写模型和 API 密钥。", "AgentBridge 模型", MessageBoxButton.OK, MessageBoxImage.Information);
                    return;
                }

                UpsertDirectProfile(profile.ModelName, profile.Provider, profile.ApiKey, profile.ApiBaseUrl);
                PersistDirectProfiles();
                RefreshModelSelector();
                dialog.Close();
                SetStatus("模型已添加");
            };
            panel.Children.Add(save);
            dialog.Content = new ScrollViewer { Content = panel };
            dialog.ShowDialog();
        }

        private static string GetComboSelectedText(ComboBox combo)
        {
            ComboBoxItem item = combo != null ? combo.SelectedItem as ComboBoxItem : null;
            return item != null ? (item.Content ?? string.Empty).ToString() : (combo != null && combo.SelectedItem != null ? combo.SelectedItem.ToString() : string.Empty);
        }

        private UIElement BuildSkillsSettingsSection()
        {
            StackPanel panel = CreateSettingsPanel("技能库");
            panel.Children.Add(CreateSettingsCard("CAD 绘图技能", "几何绘制、标注、图层整理、图纸审查。当前为内置技能，后续开放安装和启停。", "已启用", null));
            panel.Children.Add(CreateSettingsCard("开发者技能接口", "预留接口：后续支持团队增加自定义技能、版本、权限和依赖检查。", "预留", null));
            return WrapSettingsScroll(panel);
        }

        private UIElement BuildHelpSettingsSection()
        {
            StackPanel panel = CreateSettingsPanel("帮助文档");
            panel.Children.Add(CreateSettingsCard("产品说明", "打开 Web 端产品说明、部署文档和使用指南。", "打开", (sender, args) => OpenExternalUrl(BuildHelpUrl())));
            panel.Children.Add(CreateSettingsCard("网络诊断", "检查插件、本地桥、NAS backend 和模型配置。", "打开诊断", async (sender, args) => await ShowDiagnosticsPanelAsync()));
            return WrapSettingsScroll(panel);
        }

        private UIElement BuildFeedbackSettingsSection()
        {
            StackPanel panel = CreateSettingsPanel("问题反馈");
            TextBox descriptionBox = CreateSettingsTextBox("问题描述：\n操作步骤：\n期望结果：\n发生时间：");
            descriptionBox.MinHeight = 130;
            TextBox emailBox = CreateSettingsTextBox(string.Empty);
            panel.Children.Add(CreateSettingsRow("问题描述", "请描述问题、复现步骤和期望结果。", descriptionBox));
            panel.Children.Add(CreateSettingsRow("联系邮箱", "用于后续排查和回复。", emailBox));
            panel.Children.Add(CreateSettingsCard("附加信息", "默认包含插件版本、连接模式和基础配置摘要；不会上传 API Key。", "提交", (sender, args) =>
            {
                AddMessage("system", "问题反馈已记录到当前会话。后续可接入 Web 端工单接口。");
                SetStatus("反馈已记录");
            }));
            return WrapSettingsScroll(panel);
        }

        private StackPanel CreateSettingsPanel(string title)
        {
            StackPanel panel = new StackPanel();
            panel.Children.Add(new TextBlock
            {
                Text = title,
                FontSize = 24,
                FontWeight = FontWeights.SemiBold,
                Margin = new Thickness(0, 0, 0, 22),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3"))
            });
            return panel;
        }

        private static UIElement WrapSettingsScroll(UIElement content)
        {
            return new ScrollViewer
            {
                Content = content,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled
            };
        }

        private Border CreateSettingsCard(string title, string description, string actionText, RoutedEventHandler action)
        {
            Button button = null;
            if (!string.IsNullOrWhiteSpace(actionText))
            {
                button = new Button
                {
                    Content = actionText,
                    Style = (Style)FindResource("TopActionButtonStyle"),
                    Padding = new Thickness(10, 4, 10, 4),
                    BorderThickness = new Thickness(1),
                    BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#343831"))
                };
                if (action != null)
                {
                    button.Click += action;
                }
            }

            return CreateSettingsRow(title, description, button);
        }

        private Border CreateSettingsRow(string title, string description, UIElement trailing)
        {
            Grid row = new Grid();
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            StackPanel text = new StackPanel();
            text.Children.Add(new TextBlock
            {
                Text = title,
                FontSize = 13,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3"))
            });
            text.Children.Add(new TextBlock
            {
                Text = description ?? string.Empty,
                Margin = new Thickness(0, 4, 18, 0),
                TextWrapping = TextWrapping.Wrap,
                FontSize = 11,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#9DA5A0"))
            });
            row.Children.Add(text);

            if (trailing != null)
            {
                Grid.SetColumn(trailing, 1);
                row.Children.Add(trailing);
            }

            return new Border
            {
                Margin = new Thickness(0, 0, 0, 12),
                Padding = new Thickness(16, 14, 16, 14),
                CornerRadius = new CornerRadius(8),
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#242622")),
                Child = row
            };
        }

        private ComboBox CreateSettingsCombo(params string[] items)
        {
            ComboBox combo = new ComboBox
            {
                Width = 150,
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2B2D2B")),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3")),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#343831")),
                Padding = new Thickness(8, 4, 8, 4)
            };
            combo.Resources[SystemColors.WindowBrushKey] = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2B2D2B"));
            combo.Resources[SystemColors.ControlBrushKey] = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2B2D2B"));
            combo.Resources[SystemColors.ControlLightBrushKey] = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2A2D2A"));
            combo.Resources[SystemColors.ControlDarkBrushKey] = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#343831"));
            combo.Resources[SystemColors.ControlDarkDarkBrushKey] = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#343831"));
            combo.Resources[SystemColors.HighlightBrushKey] = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2A2D2A"));
            combo.Resources[SystemColors.HighlightTextBrushKey] = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#FFFFFF"));
            combo.Resources[SystemColors.ControlTextBrushKey] = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3"));
            Style darkStyle = TryFindResource("DarkComboBoxStyle") as Style;
            if (darkStyle != null)
            {
                combo.Style = darkStyle;
            }
            for (int i = 0; i < items.Length; i++)
            {
                combo.Items.Add(new ComboBoxItem
                {
                    Content = items[i],
                    Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2B2D2B")),
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3"))
                });
            }
            combo.SelectedIndex = 0;
            combo.Loaded += (sender, args) => ApplyDarkComboVisual(combo);
            combo.DropDownOpened += (sender, args) => ApplyDarkComboVisual(combo);
            return combo;
        }

        private static void ApplyDarkComboVisual(DependencyObject root)
        {
            if (root == null)
            {
                return;
            }

            SolidColorBrush background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2B2D2B"));
            SolidColorBrush borderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#343831"));
            SolidColorBrush foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3"));

            if (root is Border border)
            {
                border.Background = background;
                border.BorderBrush = borderBrush;
            }
            else if (root is ToggleButton toggleButton)
            {
                toggleButton.Background = background;
                toggleButton.BorderBrush = borderBrush;
                toggleButton.Foreground = foreground;
            }
            else if (root is ComboBoxItem item)
            {
                item.Background = background;
                item.Foreground = foreground;
            }
            else if (root is TextBlock textBlock)
            {
                textBlock.Foreground = foreground;
            }
            else if (root is Popup popup && popup.Child != null)
            {
                ApplyDarkComboVisual(popup.Child);
            }

            int childCount;
            try
            {
                childCount = VisualTreeHelper.GetChildrenCount(root);
            }
            catch (InvalidOperationException)
            {
                return;
            }

            for (int i = 0; i < childCount; i++)
            {
                ApplyDarkComboVisual(VisualTreeHelper.GetChild(root, i));
            }
        }

        private static TextBox CreateSettingsTextBox(string text)
        {
            return new TextBox
            {
                Text = text ?? string.Empty,
                Width = 260,
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#252624")),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3")),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#343831")),
                Padding = new Thickness(10, 7, 10, 7),
                TextWrapping = TextWrapping.Wrap,
                AcceptsReturn = true
            };
        }

        private static string BuildHelpUrl()
        {
            string configured = Config.Get("CADCOPILOT_HELP_URL", string.Empty).Trim();
            if (!string.IsNullOrWhiteSpace(configured))
            {
                return configured;
            }

            return "https://example.com/cadcopilot/docs";
        }

        private static void OpenExternalUrl(string url)
        {
            if (string.IsNullOrWhiteSpace(url))
            {
                return;
            }

            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(url) { UseShellExecute = true });
        }

        private async void HeaderDiagnostics_Click(object sender, RoutedEventArgs e)
        {
            CloseWorkSurfaceDrawers(DiagnosticsDrawer);
            if (DiagnosticsDrawer != null && DiagnosticsDrawer.Visibility == Visibility.Visible)
            {
                DiagnosticsDrawer.Visibility = Visibility.Collapsed;
                SetStatus("就绪");
                UpdateFooterState();
                return;
            }

            await ShowDiagnosticsPanelAsync();
        }

        private async void HeaderReview_Click(object sender, RoutedEventArgs e)
        {
            CloseWorkSurfaceDrawers(ReviewDrawer);
            if (ReviewDrawer != null && ReviewDrawer.Visibility == Visibility.Visible)
            {
                ReviewDrawer.Visibility = Visibility.Collapsed;
                SetStatus("就绪");
                UpdateFooterState();
                return;
            }

            await ShowReviewPanelAsync();
        }

        private void HeaderContext_Click(object sender, RoutedEventArgs e)
        {
            CloseWorkSurfaceDrawers(ContextDrawer);
            if (ContextDrawer != null && ContextDrawer.Visibility == Visibility.Visible)
            {
                ContextDrawer.Visibility = Visibility.Collapsed;
                SetStatus("就绪");
                UpdateFooterState();
                return;
            }

            ShowContextPanel();
        }

        private void ModelSettingsButton_Click(object sender, RoutedEventArgs e)
        {
            LoadProfileEditorForCurrentMode();
            ModelSelectorPopup.IsOpen = false;
            if (ProfileProviderPopup != null)
            {
                ProfileProviderPopup.IsOpen = false;
            }

            if (ProfileModelNamePopup != null)
            {
                ProfileModelNamePopup.IsOpen = false;
            }

            HeaderSettingsPopup.IsOpen = false;
            OpenSettingsWindow("模型");
        }

        private void ModelSelectorPopup_Opened(object sender, EventArgs e)
        {
            PositionModelSelectorPopup();
        }

        private void HeaderSettingsPopup_Opened(object sender, EventArgs e)
        {
            PositionHeaderSettingsPopup();
        }

        private void ComposerRegion_SizeChanged(object sender, SizeChangedEventArgs e)
        {
            if (ModelSelectorPopup != null && ModelSelectorPopup.IsOpen)
            {
                PositionModelSelectorPopup();
            }

            if (HeaderSettingsPopup != null && HeaderSettingsPopup.IsOpen)
            {
                PositionHeaderSettingsPopup();
            }
        }

        private void PositionModelSelectorPopup()
        {
            if (ComposerRegion == null || ModelToggleButton == null || ModelSelectorPopupShell == null)
            {
                return;
            }

            ModelSelectorPopupShell.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));
            double popupHeight = ModelSelectorPopupShell.ActualHeight > 0
                ? ModelSelectorPopupShell.ActualHeight
                : ModelSelectorPopupShell.DesiredSize.Height;

            Point anchor = ModelToggleButton.TransformToAncestor(ComposerRegion).Transform(new Point(0, 0));
            ModelSelectorPopup.HorizontalOffset = Math.Max(0, anchor.X);
            ModelSelectorPopup.VerticalOffset = anchor.Y - popupHeight - 10;
        }

        private void PositionHeaderSettingsPopup()
        {
            if (ComposerRegion == null || HeaderSettingsPopupShell == null)
            {
                return;
            }

            double popupWidth = Math.Max(320, ComposerRegion.ActualWidth);
            HeaderSettingsPopupShell.Width = popupWidth;
            HeaderSettingsPopupShell.Measure(new Size(popupWidth, double.PositiveInfinity));

            double popupHeight = HeaderSettingsPopupShell.ActualHeight > 0
                ? HeaderSettingsPopupShell.ActualHeight
                : HeaderSettingsPopupShell.DesiredSize.Height;

            HeaderSettingsPopup.HorizontalOffset = 0;
            HeaderSettingsPopup.VerticalOffset = -popupHeight - 10;
        }

        private async void HeaderTaskCenter_Click(object sender, RoutedEventArgs e)
        {
            CloseWorkSurfaceDrawers(TaskCenterDrawer);
            await ShowRecentTasksPanelAsync();
        }

        private void HeaderExpand_Click(object sender, RoutedEventArgs e)
        {
            CopilotPalette.ToggleExpandedLayout();
            AddMessage("system", "Panel Shell 已切换布局宽度，便于查看更长的对话和工具区域。");
        }

        private void HeaderClose_Click(object sender, RoutedEventArgs e)
        {
            CopilotPalette.Hide();
        }

        private void OpenAttachmentMenu_Click(object sender, RoutedEventArgs e)
        {
            Button button = sender as Button;
            if (button == null || button.ContextMenu == null)
            {
                return;
            }

            button.ContextMenu.PlacementTarget = button;
            button.ContextMenu.IsOpen = true;
        }

        private void UploadImage_Click(object sender, RoutedEventArgs e)
        {
            OpenFileDialog dialog = new OpenFileDialog
            {
                Title = "选择图纸截图",
                Filter = "图片文件|*.png;*.jpg;*.jpeg;*.bmp;*.gif|所有文件|*.*"
            };

            if (dialog.ShowDialog() == true)
            {
                LoadImage(dialog.FileName);
            }
        }

        private void UploadFile_Click(object sender, RoutedEventArgs e)
        {
            OpenFileDialog dialog = new OpenFileDialog
            {
                Title = "选择文本附件",
                Filter = "文本与文档|*.txt;*.md;*.markdown;*.json;*.csv;*.log;*.cs;*.xaml;*.xml;*.docx|所有文件|*.*"
            };

            if (dialog.ShowDialog() == true)
            {
                LoadTextAttachment(dialog.FileName);
            }
        }

        private void PasteImageMenu_Click(object sender, RoutedEventArgs e)
        {
            if (!Clipboard.ContainsImage())
            {
                AddMessage("system", "剪贴板中没有可用图片。请先复制截图，再执行粘贴。");
                return;
            }

            BitmapSource image = Clipboard.GetImage();
            if (image == null)
            {
                return;
            }

            SetPendingImage(image, "pasted-image.png");
        }

        private void RemoveAttachment_Click(object sender, RoutedEventArgs e)
        {
            ClearPendingAttachment();
        }

        private void OnPaste(object sender, DataObjectPastingEventArgs e)
        {
            if (!Clipboard.ContainsImage())
            {
                return;
            }

            e.CancelCommand();
            BitmapSource image = Clipboard.GetImage();
            if (image == null)
            {
                return;
            }

            SetPendingImage(image, "pasted-image.png");
        }

        private void LoadImage(string filePath)
        {
            try
            {
                BitmapImage image = new BitmapImage();
                image.BeginInit();
                image.UriSource = new Uri(filePath);
                image.DecodePixelWidth = 100;
                image.CacheOption = BitmapCacheOption.OnLoad;
                image.EndInit();
                image.Freeze();

                _pendingImage = File.ReadAllBytes(filePath);
                _pendingAttachmentName = Path.GetFileName(filePath);
                _pendingAttachmentKind = "图片";
                _pendingAttachmentText = null;
                _pendingAttachmentMeta = "图片附件将随本次消息一起发送。";
                ShowImagePreview(image);
            }
            catch (Exception ex)
            {
                AddMessage("error", "图片加载失败: " + ex.Message);
            }
        }

        private void LoadTextAttachment(string filePath)
        {
            try
            {
                string extension = Path.GetExtension(filePath) ?? string.Empty;
                string rawText = ExtractAttachmentText(filePath, extension);
                if (string.IsNullOrWhiteSpace(rawText))
                {
                    throw new InvalidOperationException("文件内容为空，或当前格式暂不支持。");
                }

                bool truncated;
                _pendingAttachmentText = TruncateAttachmentText(rawText, 12000, out truncated);
                _pendingAttachmentName = Path.GetFileName(filePath);
                _pendingAttachmentKind = "文件";
                _pendingImage = null;
                _pendingAttachmentMeta = truncated
                    ? "文本附件已提取并截断为前 12000 个字符。"
                    : "文本附件将随本次消息一起发送。";

                ShowFilePreview(_pendingAttachmentName, extension, _pendingAttachmentMeta);
            }
            catch (Exception ex)
            {
                AddMessage("error", "附件读取失败: " + ex.Message);
            }
        }

        private void ShowImagePreview(ImageSource image)
        {
            ImagePreview.Source = image;
            ImagePreview.Visibility = Visibility.Visible;
            AttachmentGlyphText.Visibility = Visibility.Collapsed;
            AttachmentTitleText.Text = _pendingAttachmentName;
            AttachmentMetaText.Text = _pendingAttachmentMeta;
            AttachmentShelf.Visibility = Visibility.Visible;
        }

        private void ShowFilePreview(string fileName, string extension, string meta)
        {
            ImagePreview.Source = null;
            ImagePreview.Visibility = Visibility.Collapsed;
            AttachmentGlyphText.Visibility = Visibility.Visible;
            AttachmentGlyphText.Text = BuildAttachmentGlyph(extension);
            AttachmentTitleText.Text = fileName;
            AttachmentMetaText.Text = meta;
            AttachmentShelf.Visibility = Visibility.Visible;
        }

        private Border CreateMessageBubble(string role, string content, out TextBox contentText)
        {
            Border bubble = new Border
            {
                CornerRadius = new CornerRadius(9),
                BorderThickness = new Thickness(1)
            };
            bubble.Tag = role;
            contentText = new TextBox
            {
                Text = content,
                IsReadOnly = true,
                IsReadOnlyCaretVisible = true,
                AcceptsReturn = true,
                TextWrapping = TextWrapping.Wrap,
                FontSize = 12.3,
                BorderThickness = new Thickness(0),
                Padding = new Thickness(0),
                Margin = new Thickness(0),
                Background = Brushes.Transparent,
                VerticalScrollBarVisibility = ScrollBarVisibility.Disabled,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
                SelectionBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#4A8DDE")),
                SelectionOpacity = 0.30,
                CaretBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#9CCBFF")),
                Cursor = Cursors.IBeam,
                ContextMenu = CreateReadOnlyTextContextMenu(),
                MinWidth = 32
            };
            contentText.PreviewMouseLeftButtonDown += ReadOnlyTextBox_PreviewMouseLeftButtonDown;
            contentText.PreviewKeyDown += ReadOnlyTextBox_PreviewKeyDown;
            bubble.Child = contentText;
            ApplyMessageBubbleStyle(bubble, contentText, role);
            return bubble;
        }

        private void ApplyMessageBubbleStyle(Border bubble, TextBox contentText, string role)
        {
            Brush background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2A2A2A"));
            Brush foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#E3E7EB"));
            Brush borderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#383C42"));
            HorizontalAlignment alignment = HorizontalAlignment.Left;
            Thickness padding = new Thickness(12, 9, 12, 9);
            Thickness margin = new Thickness(0, 0, 54, 0);
            double fontSize = 12.3;
            Thickness borderThickness = new Thickness(1);

            if (string.Equals(role, "user", StringComparison.OrdinalIgnoreCase))
            {
                background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#31353D"));
                foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#E6EAEE"));
                borderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#49525F"));
                alignment = HorizontalAlignment.Right;
                margin = new Thickness(54, 0, 0, 0);
            }
            else if (string.Equals(role, "assistant", StringComparison.OrdinalIgnoreCase))
            {
                background = Brushes.Transparent;
                borderBrush = Brushes.Transparent;
                padding = new Thickness(0, 2, 0, 2);
                margin = new Thickness(0, 0, 48, 0);
                borderThickness = new Thickness(0);
            }
            else if (string.Equals(role, "system", StringComparison.OrdinalIgnoreCase))
            {
                background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#232323"));
                foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#A9B1BA"));
                borderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#343941"));
                alignment = HorizontalAlignment.Center;
                margin = new Thickness(24, 0, 24, 0);
                fontSize = 11;
                padding = new Thickness(11, 6, 11, 6);
            }
            else if (string.Equals(role, "error", StringComparison.OrdinalIgnoreCase))
            {
                background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#432D33"));
                foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#FFD7DD"));
                borderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#915965"));
            }

            bubble.Background = background;
            bubble.BorderBrush = borderBrush;
            bubble.Padding = padding;
            bubble.Margin = margin;
            bubble.HorizontalAlignment = alignment;
            bubble.BorderThickness = borderThickness;
            bubble.MaxWidth = CalculateMessageBubbleMaxWidth(role);
            contentText.FontSize = fontSize;
            contentText.Foreground = foreground;
        }

        private void SetStatus(string status)
        {
            _currentStatus = status;
            Dispatcher.Invoke(() =>
            {
                StatusText.Text = "AgentBridge / " + status;
                UpdateFooterState();
            });
        }

        private void ReloadClient()
        {
            _llmClient = new ClaudeClient();
        }

        private void LoadSettingsIntoView()
        {
            _isLoadingSettings = true;
            LoadDirectProfiles();
            LoadServiceProfiles();
            SelectComboBoxTag(ConnectionModeBox, GetConfiguredConnectionMode());
            SelectComboBoxTag(AgentApprovalBox, GetConfiguredAgentApprovalMode());
            SelectComboBoxTag(ProviderBox, GetConfiguredProvider());
            SelectComboBoxTag(ProfileProviderBox, GetConfiguredProvider());
            ApiBaseUrlBox.Text = Config.Get("CADCOPILOT_API_BASE_URL", "http://127.0.0.1:8000");
            DirectApiBaseUrlBox.Text = Config.Get("OPENAI_API_BASE_URL", GetProviderDefaultBaseUrl(GetConfiguredProvider()));
            LoadDirectSettingsForProvider();
            PopulateProfileModelOptions(GetConfiguredProvider(), GetCurrentUiModel());
            RefreshModelSelector();
            _isLoadingSettings = false;
            UpdateConfigEditorState();
            UpdateFooterState();
        }

        private void InitializeToolbar()
        {
            ToolboxList.ItemsSource = AllTools;
            for (int i = 0; i < AllTools.Length; i++)
            {
                _pinnedTools.Add(AllTools[i]);
            }
            PinnedToolBar.ItemsSource = _pinnedTools;
        }

        private void RefreshModelSelector()
        {
            string currentModel = GetCurrentUiModel();
            string[] options = GetUnifiedModelNames();
            ModelLabelText.Text = "模型";

            ModelSelector.Items.Clear();
            for (int i = 0; i < options.Length; i++)
            {
                ModelSelector.Items.Add(options[i]);
            }

            bool hasCurrent = false;
            foreach (object item in ModelSelector.Items)
            {
                if (string.Equals(item as string, currentModel, StringComparison.OrdinalIgnoreCase))
                {
                    hasCurrent = true;
                    break;
                }
            }

            if (!hasCurrent && !string.IsNullOrWhiteSpace(currentModel))
            {
                ModelSelector.Items.Add(currentModel);
            }

            ModelSelector.SelectedItem = currentModel;
            ModelSelectorText.Text = currentModel;
            BuildModelSelectorPopup(options, currentModel);
            UpdateFooterState();
        }

        private void BuildModelSelectorPopup(string[] options, string currentModel)
        {
            ModelSelectorPanel.Children.Clear();
            for (int i = 0; i < options.Length; i++)
            {
                string option = options[i];
                ModelSelectorPanel.Children.Add(BuildModelSelectorOptionButton(option, currentModel));
            }

            Border divider = new Border
            {
                Height = 1,
                Margin = new Thickness(4, 6, 4, 6),
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#2D333B"))
            };
            ModelSelectorPanel.Children.Add(divider);
            ModelSelectorPanel.Children.Add(BuildModelSelectorOptionButton("管理模型设置...", currentModel, ModelManagerOption));
        }

        private Button BuildModelSelectorOptionButton(string labelText, string currentModel, string tag = null)
        {
            Button button = new Button
            {
                Tag = tag ?? labelText,
                Style = (Style)FindResource("PopupMenuItemButtonStyle")
            };

            Grid layout = new Grid();
            layout.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            layout.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            TextBlock label = new TextBlock
            {
                Text = labelText,
                VerticalAlignment = VerticalAlignment.Center,
                FontSize = 10.8,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#C8CDD4"))
            };
            layout.Children.Add(label);

            TextBlock suffix = new TextBlock
            {
                Text = string.Equals(tag, ModelManagerOption, StringComparison.OrdinalIgnoreCase) ? "设置" : BuildModelSelectorSuffix(labelText, currentModel),
                VerticalAlignment = VerticalAlignment.Center,
                FontSize = 9.5,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#8B949E"))
            };
            Grid.SetColumn(suffix, 1);
            layout.Children.Add(suffix);

            button.Content = layout;
            button.Click += ModelOption_Click;
            return button;
        }

        private bool UseServiceMode()
        {
            return string.Equals(GetSelectedConnectionMode(), ConnectionModeService, StringComparison.OrdinalIgnoreCase);
        }

        private void ToggleConfig_Click(object sender, RoutedEventArgs e)
        {
            if (TaskCenterDrawer != null)
            {
                TaskCenterDrawer.Visibility = Visibility.Collapsed;
            }

            ConfigDrawer.Visibility = ConfigDrawer.Visibility == Visibility.Visible ? Visibility.Collapsed : Visibility.Visible;
            UpdateFooterState();
        }

        private void SaveConfig_Click(object sender, RoutedEventArgs e)
        {
            string connectionMode = GetSelectedConnectionMode();
            string provider = GetSelectedProvider();
            string apiBaseUrl = (ApiBaseUrlBox.Text ?? string.Empty).Trim();
            string directApiKey = (DirectApiKeyBox.Text ?? string.Empty).Trim();
            string directApiBaseUrl = string.IsNullOrWhiteSpace(DirectApiBaseUrlBox.Text) ? GetProviderDefaultBaseUrl(provider) : DirectApiBaseUrlBox.Text.Trim();
            string selectedModel = string.IsNullOrWhiteSpace(ModelSelector.Text)
                ? GetDefaultDirectModel(provider)
                : ModelSelector.Text.Trim();

            Config.Set("CADCOPILOT_CONNECTION_MODE", connectionMode);
            Config.Set("CADCOPILOT_AGENT_APPROVAL", GetSelectedAgentApprovalMode());
            Config.Set("CADCOPILOT_API_BASE_URL", apiBaseUrl);
            Config.Set("LLM_PROVIDER", provider);
            Config.Set("OPENAI_API_BASE_URL", directApiBaseUrl);

            Config.Set("OPENAI_API_KEY", directApiKey);
            Config.Set("OPENAI_MODEL", selectedModel);
            Config.Set("ACTIVE_DIRECT_MODEL", selectedModel);
            Config.Set("ACTIVE_SERVICE_MODEL", selectedModel);
            Config.Set("CADCOPILOT_MODEL", selectedModel);
            UpsertDirectProfile(selectedModel, provider, directApiKey, directApiBaseUrl);
            PersistDirectProfiles();

            ReloadClient();
            DirectModelBox.Text = selectedModel;
            RefreshModelSelector();
            SetStatus("配置已保存");
            ConfigDrawer.Visibility = Visibility.Collapsed;
        }

        private async void OpenDiagnosticsFromSettings_Click(object sender, RoutedEventArgs e)
        {
            CloseWorkSurfaceDrawers(DiagnosticsDrawer);
            await ShowDiagnosticsPanelAsync();
        }
        private void NewConversation_Click(object sender, RoutedEventArgs e)
        {
            CreateConversationTab();
        }

        private void FutureTool_Click(object sender, RoutedEventArgs e)
        {
            if (_pinnedTools.Count >= MaxPinnedTools)
            {
                AddMessage("system", "常驻工具栏最多保留 5 个工具。请先拖拽重排，或移除一个再添加。");
                return;
            }
        }

        private void ApiBaseUrlBox_TextChanged(object sender, TextChangedEventArgs e)
        {
            if (_isLoadingSettings)
            {
                return;
            }

            RefreshModelSelector();
            UpdateFooterState();
        }

        private void ConnectionModeBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            if (_isLoadingSettings)
            {
                return;
            }

            Config.Set("CADCOPILOT_CONNECTION_MODE", GetSelectedConnectionMode());
            if (!UseServiceMode())
            {
                ClearTaskStepper();
                ClearTaskCenter();
            }
            ReloadClient();
            UpdateConfigEditorState();
            RefreshModelSelector();
        }

        private void AgentApprovalBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            if (_isLoadingSettings)
            {
                return;
            }

            Config.Set("CADCOPILOT_AGENT_APPROVAL", GetSelectedAgentApprovalMode());
            UpdateConnectionModeButtonVisual();
            UpdateFooterState();
        }

        private void AgentApprovalComposerButton_Click(object sender, RoutedEventArgs e)
        {
            ContextMenu menu = new ContextMenu();
            menu.Items.Add(CreateAgentApprovalMenuItem("请求批准", AgentApprovalAnnotate));
            menu.Items.Add(CreateAgentApprovalMenuItem("替我执行", AgentApprovalExecute));
            menu.Items.Add(CreateAgentApprovalMenuItem("完全批准", AgentApprovalFull));
            menu.PlacementTarget = AgentApprovalComposerButton;
            menu.Placement = PlacementMode.Top;
            menu.IsOpen = true;
        }

        private MenuItem CreateAgentApprovalMenuItem(string label, string mode)
        {
            MenuItem item = new MenuItem
            {
                Header = label,
                Tag = mode,
                IsCheckable = true,
                IsChecked = string.Equals(GetConfiguredAgentApprovalMode(), mode, StringComparison.OrdinalIgnoreCase)
            };
            item.Click += (sender, args) => ApplyAgentApprovalMode((sender as MenuItem)?.Tag as string);
            return item;
        }

        private void ApplyAgentApprovalMode(string mode)
        {
            string normalized = NormalizeAgentApprovalMode(mode);
            Config.Set("CADCOPILOT_AGENT_APPROVAL", normalized);
            SelectComboBoxTag(AgentApprovalBox, normalized);
            ReloadClient();
            UpdateConnectionModeButtonVisual();
            SetStatus(GetAgentApprovalDisplayName(normalized));
        }

        private void ProviderBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            if (_isLoadingSettings)
            {
                return;
            }

            LoadDirectSettingsForProvider();
            UpdateConfigEditorState();
            RefreshModelSelector();
        }

        private void ModelSelector_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            SaveSelectedModel();
        }

        private void ModelSelector_LostFocus(object sender, RoutedEventArgs e)
        {
            SaveSelectedModel();
        }

        private void SaveSelectedModel()
        {
            if (_isLoadingSettings)
            {
                return;
            }

            string model = ((ModelSelector.SelectedItem as string) ?? (ModelSelector.Text ?? string.Empty)).Trim();
            if (string.IsNullOrWhiteSpace(model))
            {
                return;
            }

            ApplyModelSelection(model);

            ReloadClient();
            ModelSelectorText.Text = model;
            BuildModelSelectorPopup(GetUnifiedModelNames(), model);
            UpdateFooterState();
        }

        private void ModelToggleButton_Click(object sender, RoutedEventArgs e)
        {
            RefreshModelSelector();
            ModelSelectorPopup.IsOpen = !ModelSelectorPopup.IsOpen;
        }

        private void ModelOption_Click(object sender, RoutedEventArgs e)
        {
            Button button = sender as Button;
            string model = button != null ? button.Tag as string : null;
            if (string.IsNullOrWhiteSpace(model))
            {
                return;
            }

            if (string.Equals(model, ModelManagerOption, StringComparison.OrdinalIgnoreCase))
            {
                ModelSelectorPopup.IsOpen = false;
                OpenSettingsDrawer("模型设置");
                return;
            }

            ModelSelector.SelectedItem = model;
            SaveSelectedModel();
            ModelSelectorPopup.IsOpen = false;
        }

        private void ToolboxToggleButton_Click(object sender, RoutedEventArgs e)
        {
            ToolboxPopup.IsOpen = !ToolboxPopup.IsOpen;
        }

        private void ToolboxPopup_Closed(object sender, EventArgs e)
        {
            _draggingToolKey = null;
            _draggingFromPinnedBar = false;
        }

        private void ToolboxItem_Click(object sender, RoutedEventArgs e)
        {
            string toolKey = GetToolKeyFromSender(sender);
            if (string.IsNullOrWhiteSpace(toolKey))
            {
                return;
            }

            AddPinnedTool(toolKey);
        }

        private void ToolboxItem_PreviewMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
        {
            _dragStartPoint = e.GetPosition(null);
            _draggingToolKey = GetToolKeyFromSender(sender);
            _draggingFromPinnedBar = false;
        }

        private void ToolboxItem_MouseMove(object sender, MouseEventArgs e)
        {
            if (e.LeftButton != MouseButtonState.Pressed)
            {
                return;
            }

            StartToolDragIfNeeded(e.GetPosition(null));
        }

        private void PinnedToolButton_Click(object sender, RoutedEventArgs e)
        {
            string toolKey = GetToolKeyFromSender(sender);
            ToolDefinition tool = FindTool(toolKey);
            if (tool == null)
            {
                return;
            }

            ApplySmartToolbarPrompt(tool);
        }

        private void ApplySmartToolbarPrompt(ToolDefinition tool)
        {
            if (tool == null)
            {
                return;
            }

            if (tool.RequiresAgent)
            {
                ApplyConnectionMode(ConnectionModeService);
            }

            InputBox.Text = tool.Prompt ?? string.Empty;
            InputBox.CaretIndex = InputBox.Text.Length;
            FocusInputBox(true);
            AddMessage("system", "已选择“" + tool.Name + "”。请补充必要参数后发送，复杂写图会先生成预览再确认。");
        }

        private void RemovePinnedTool_Click(object sender, RoutedEventArgs e)
        {
            MenuItem menuItem = sender as MenuItem;
            if (menuItem == null)
            {
                return;
            }

            ContextMenu contextMenu = menuItem.Parent as ContextMenu;
            Button targetButton = contextMenu != null ? contextMenu.PlacementTarget as Button : null;
            string toolKey = targetButton != null ? targetButton.Tag as string : null;
            if (string.IsNullOrWhiteSpace(toolKey))
            {
                return;
            }

            RemovePinnedTool(toolKey);
        }

        private void PinnedToolButton_PreviewMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
        {
            _dragStartPoint = e.GetPosition(null);
            _draggingToolKey = GetToolKeyFromSender(sender);
            _draggingFromPinnedBar = true;
        }

        private void PinnedToolButton_MouseMove(object sender, MouseEventArgs e)
        {
            if (e.LeftButton != MouseButtonState.Pressed)
            {
                return;
            }

            StartToolDragIfNeeded(e.GetPosition(null));
        }

        private void PinnedToolBar_PreviewDragOver(object sender, DragEventArgs e)
        {
            if (!e.Data.GetDataPresent(DataFormats.StringFormat))
            {
                e.Effects = DragDropEffects.None;
                e.Handled = true;
                return;
            }

            string toolKey = e.Data.GetData(DataFormats.StringFormat) as string;
            if (string.IsNullOrWhiteSpace(toolKey))
            {
                e.Effects = DragDropEffects.None;
            }
            else if (_draggingFromPinnedBar || _pinnedTools.Count < MaxPinnedTools || ContainsPinnedTool(toolKey))
            {
                e.Effects = DragDropEffects.Move;
            }
            else
            {
                e.Effects = DragDropEffects.None;
            }

            e.Handled = true;
        }

        private void PinnedToolBar_Drop(object sender, DragEventArgs e)
        {
            if (!e.Data.GetDataPresent(DataFormats.StringFormat))
            {
                return;
            }

            string toolKey = e.Data.GetData(DataFormats.StringFormat) as string;
            if (string.IsNullOrWhiteSpace(toolKey))
            {
                return;
            }

            Button targetButton = FindAncestor<Button>(e.OriginalSource as DependencyObject);
            int targetIndex = ResolveDropIndex(targetButton);
            MovePinnedTool(toolKey, targetIndex);
        }

        private void StartToolDragIfNeeded(Point currentPoint)
        {
            if (string.IsNullOrWhiteSpace(_draggingToolKey))
            {
                return;
            }

            if (Math.Abs(currentPoint.X - _dragStartPoint.X) < SystemParameters.MinimumHorizontalDragDistance &&
                Math.Abs(currentPoint.Y - _dragStartPoint.Y) < SystemParameters.MinimumVerticalDragDistance)
            {
                return;
            }

            DragDrop.DoDragDrop(this, new DataObject(DataFormats.StringFormat, _draggingToolKey), DragDropEffects.Move);
        }

        private void AddPinnedTool(string toolKey)
        {
            if (ContainsPinnedTool(toolKey))
            {
                MovePinnedTool(toolKey, _pinnedTools.Count - 1);
                return;
            }

            if (_pinnedTools.Count >= MaxPinnedTools)
            {
                AddMessage("system", "常驻工具栏已满。当前最多支持 5 个工具。");
                return;
            }

            ToolDefinition tool = FindTool(toolKey);
            if (tool == null)
            {
                return;
            }

            _pinnedTools.Add(tool);
            ToolboxPopup.IsOpen = false;
        }

        private void RemovePinnedTool(string toolKey)
        {
            ToolDefinition tool = FindPinnedTool(toolKey);
            if (tool == null)
            {
                return;
            }

            _pinnedTools.Remove(tool);
            AddMessage("system", tool.Name + " 已从常用工具栏移除。仍可在上方开放式工具技能包中再次加入。");
        }

        private void MovePinnedTool(string toolKey, int targetIndex)
        {
            ToolDefinition tool = FindPinnedTool(toolKey);
            if (tool == null)
            {
                if (_pinnedTools.Count >= MaxPinnedTools)
                {
                    AddMessage("system", "常驻工具栏已满。当前最多支持 5 个工具。");
                    return;
                }

                tool = FindTool(toolKey);
                if (tool == null)
                {
                    return;
                }

                if (targetIndex < 0 || targetIndex > _pinnedTools.Count)
                {
                    targetIndex = _pinnedTools.Count;
                }

                _pinnedTools.Insert(targetIndex, tool);
                ToolboxPopup.IsOpen = false;
                return;
            }

            int sourceIndex = _pinnedTools.IndexOf(tool);
            if (sourceIndex < 0)
            {
                return;
            }

            if (targetIndex < 0 || targetIndex >= _pinnedTools.Count)
            {
                targetIndex = _pinnedTools.Count - 1;
            }

            if (sourceIndex == targetIndex)
            {
                return;
            }

            _pinnedTools.Move(sourceIndex, targetIndex);
        }

        private int ResolveDropIndex(Button targetButton)
        {
            if (targetButton == null)
            {
                return _pinnedTools.Count;
            }

            string targetKey = targetButton.Tag as string;
            if (string.IsNullOrWhiteSpace(targetKey))
            {
                return _pinnedTools.Count;
            }

            ToolDefinition targetTool = FindPinnedTool(targetKey);
            return targetTool == null ? _pinnedTools.Count : _pinnedTools.IndexOf(targetTool);
        }

        private bool ContainsPinnedTool(string toolKey)
        {
            return FindPinnedTool(toolKey) != null;
        }

        private ToolDefinition FindPinnedTool(string toolKey)
        {
            for (int i = 0; i < _pinnedTools.Count; i++)
            {
                if (string.Equals(_pinnedTools[i].Key, toolKey, StringComparison.OrdinalIgnoreCase))
                {
                    return _pinnedTools[i];
                }
            }

            return null;
        }

        private static string GetToolKeyFromSender(object sender)
        {
            Button button = sender as Button;
            return button != null ? button.Tag as string : null;
        }

        private static T FindAncestor<T>(DependencyObject source) where T : DependencyObject
        {
            DependencyObject current = source;
            while (current != null)
            {
                T typed = current as T;
                if (typed != null)
                {
                    return typed;
                }

                current = VisualTreeHelper.GetParent(current);
            }

            return null;
        }

        private static ToolDefinition FindTool(string toolKey)
        {
            for (int i = 0; i < AllTools.Length; i++)
            {
                if (string.Equals(AllTools[i].Key, toolKey, StringComparison.OrdinalIgnoreCase))
                {
                    return AllTools[i];
                }
            }

            return null;
        }

        private void CodeModeButton_Click(object sender, RoutedEventArgs e)
        {
            ContextMenu menu = new ContextMenu();
            menu.Items.Add(CreateModeMenuItem("标准", ConnectionModeStandard));
            menu.Items.Add(CreateModeMenuItem("智能体", ConnectionModeService));
            menu.PlacementTarget = CodeModeButton;
            menu.Placement = PlacementMode.Top;
            menu.IsOpen = true;
        }

        private MenuItem CreateModeMenuItem(string label, string mode)
        {
            MenuItem item = new MenuItem
            {
                Header = label,
                Tag = mode,
                IsCheckable = true,
                IsChecked = string.Equals(GetSelectedConnectionMode(), mode, StringComparison.OrdinalIgnoreCase)
            };
            item.Click += (sender, args) => ApplyConnectionMode((sender as MenuItem)?.Tag as string);
            return item;
        }

        private void ApplyConnectionMode(string mode)
        {
            mode = NormalizeConnectionMode(mode);
            if (string.Equals(mode, ConnectionModeService, StringComparison.OrdinalIgnoreCase) && string.IsNullOrWhiteSpace(Config.Get("CADCOPILOT_API_BASE_URL", string.Empty)))
            {
                Config.Set("CADCOPILOT_API_BASE_URL", "http://127.0.0.1:8000");
                ApiBaseUrlBox.Text = "http://127.0.0.1:8000";
            }

            Config.Set("CADCOPILOT_CONNECTION_MODE", mode);
            SelectComboBoxTag(ConnectionModeBox, mode);
            ReloadClient();
            UpdateConnectionModeButtonVisual();
            if (!UseServiceMode())
            {
                ClearTaskStepper();
                ClearTaskCenter();
            }

            string modeLabel = GetConnectionModeDisplayName(GetSelectedConnectionMode());
            SetStatus(modeLabel);
            UpdateFooterState();
            RefreshModelSelector();
        }

        private void InputBox_TextChanged(object sender, TextChangedEventArgs e)
        {
            UpdateInputPlaceholder();
        }

        private void ChatPanel_Loaded(object sender, RoutedEventArgs e)
        {
            RefreshMessageBubbleWidths();
            FocusInputBox(true);
        }

        private void ChatPanel_SizeChanged(object sender, SizeChangedEventArgs e)
        {
            RefreshMessageBubbleWidths();
        }

        private void MessageScroller_SizeChanged(object sender, SizeChangedEventArgs e)
        {
            RefreshMessageBubbleWidths();
        }

        private void InputBox_GotFocus(object sender, RoutedEventArgs e)
        {
            _isInputFocused = true;
            UpdateInputPlaceholder();
            UpdateComposerFocusVisual();
        }

        private void InputBox_LostFocus(object sender, RoutedEventArgs e)
        {
            _isInputFocused = false;
            UpdateInputPlaceholder();
            UpdateComposerFocusVisual();
        }

        private void ComposerRegion_PreviewMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
        {
            DependencyObject source = e.OriginalSource as DependencyObject;
            if (FindAncestor<Button>(source) != null ||
                FindAncestor<TextBox>(source) != null ||
                FindAncestor<ComboBox>(source) != null ||
                FindAncestor<ScrollBar>(source) != null ||
                FindAncestor<MenuItem>(source) != null)
            {
                return;
            }

            FocusInputBox(true);
        }

        private void UpdateInputPlaceholder()
        {
            bool isEmpty = string.IsNullOrWhiteSpace(InputBox.Text);
            InputPlaceholderText.Visibility = isEmpty && !_isInputFocused ? Visibility.Visible : Visibility.Collapsed;
        }

        private void UpdateComposerFocusVisual()
        {
            Brush focusBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(_isInputFocused ? "#58A6FF" : "#3A3D41"));
            ComposerRegion.BorderBrush = focusBrush;
        }

        private void AddWelcomeMessage()
        {
            AddMessage("assistant", "你好，我是 AgentBridge。可以直接描述绘图、审查或标注需求；复杂任务切到智能体模式后，我会先生成更改预览，确认后再应用到当前图纸。");
        }

        private void InitializeConversationTabs()
        {
            if (_conversationSessions.Count > 0)
            {
                return;
            }

            ConversationSession session = new ConversationSession
            {
                Id = Guid.NewGuid().ToString("N"),
                Title = "会话",
                MessageChildren = CaptureMessageChildren(clear: false)
            };
            _conversationSessions.Add(session);
            _activeConversationId = session.Id;
            RenderConversationTabs();
        }

        private void CreateConversationTab()
        {
            SaveActiveConversationMessages();
            ClearTaskStepper();
            ClearTaskCenter();
            ClearReviewPanel();
            ClearContextPanel();
            ClearPendingAttachment();
            if (_llmClient != null)
            {
                _llmClient.ResetPlannerSession();
            }

            _conversationSequence++;
            ConversationSession session = new ConversationSession
            {
                Id = Guid.NewGuid().ToString("N"),
                Title = "新会话",
                MessageChildren = new List<UIElement>()
            };
            _conversationSessions.Add(session);
            _activeConversationId = session.Id;
            MessageList.Children.Clear();
            AddWelcomeMessage();
            SaveActiveConversationMessages();
            RenderConversationTabs();
            SetStatus("新会话");
        }

        private void SwitchConversation(string sessionId)
        {
            if (string.IsNullOrWhiteSpace(sessionId) || string.Equals(sessionId, _activeConversationId, StringComparison.OrdinalIgnoreCase))
            {
                return;
            }

            SaveActiveConversationMessages();
            ConversationSession target = FindConversation(sessionId);
            if (target == null)
            {
                return;
            }

            _activeConversationId = target.Id;
            MessageList.Children.Clear();
            List<UIElement> children = target.MessageChildren ?? new List<UIElement>();
            for (int i = 0; i < children.Count; i++)
            {
                MessageList.Children.Add(children[i]);
            }

            ClearTaskStepper();
            ClearTaskCenter();
            RenderConversationTabs();
            RefreshMessageBubbleWidths();
            MessageScroller.ScrollToEnd();
            SetStatus(target.Title);
        }

        private void SaveActiveConversationMessages()
        {
            ConversationSession active = FindConversation(_activeConversationId);
            if (active != null)
            {
                active.MessageChildren = CaptureMessageChildren(clear: false);
            }
        }

        private List<UIElement> CaptureMessageChildren(bool clear)
        {
            List<UIElement> children = new List<UIElement>();
            for (int i = 0; i < MessageList.Children.Count; i++)
            {
                UIElement child = MessageList.Children[i];
                if (child != null)
                {
                    children.Add(child);
                }
            }

            if (clear)
            {
                MessageList.Children.Clear();
            }

            return children;
        }

        private ConversationSession FindConversation(string sessionId)
        {
            for (int i = 0; i < _conversationSessions.Count; i++)
            {
                ConversationSession session = _conversationSessions[i];
                if (session != null && string.Equals(session.Id, sessionId, StringComparison.OrdinalIgnoreCase))
                {
                    return session;
                }
            }

            return null;
        }

        private void RenderConversationTabs()
        {
            if (ConversationTabsPanel == null)
            {
                return;
            }

            ConversationTabsPanel.Children.Clear();
            for (int i = 0; i < _conversationSessions.Count; i++)
            {
                ConversationSession session = _conversationSessions[i];
                if (session == null)
                {
                    continue;
                }

                bool isActive = string.Equals(session.Id, _activeConversationId, StringComparison.OrdinalIgnoreCase);
                Grid tabLayout = new Grid();
                tabLayout.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                tabLayout.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                TextBlock title = new TextBlock
                {
                    Text = session.Title,
                    VerticalAlignment = VerticalAlignment.Center,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString(isActive ? "#F3F3F3" : "#8B949E"))
                };
                Button closeButton = new Button
                {
                    Content = "×",
                    Tag = session.Id,
                    Style = (Style)FindResource("TopActionButtonStyle"),
                    Padding = new Thickness(4, 0, 0, 0),
                    Margin = new Thickness(6, 0, 0, 0),
                    Visibility = _conversationSessions.Count > 1 ? Visibility.Visible : Visibility.Collapsed,
                    ToolTip = "关闭会话"
                };
                closeButton.Click += CloseConversationTab_Click;
                Grid.SetColumn(closeButton, 1);
                tabLayout.Children.Add(title);
                tabLayout.Children.Add(closeButton);

                Button tab = new Button
                {
                    Content = tabLayout,
                    Tag = session.Id,
                    Style = (Style)FindResource("TopActionButtonStyle"),
                    Padding = new Thickness(12, 8, 10, 8),
                    Margin = new Thickness(0, 0, 1, 0),
                    BorderThickness = new Thickness(1),
                    BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(
                        isActive ? "#323438" : "#2A2D31")),
                    Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString(
                        isActive ? "#1E1E1E" : "#171717"))
                };
                tab.Click += ConversationTab_Click;
                ConversationTabsPanel.Children.Add(tab);
            }
        }

        private void UpdateActiveConversationTitleFromPrompt(string prompt, string attachmentName)
        {
            ConversationSession active = FindConversation(_activeConversationId);
            if (active == null || !IsUntitledConversation(active.Title))
            {
                return;
            }

            string titleSource = !string.IsNullOrWhiteSpace(prompt) ? prompt : attachmentName;
            string title = BuildConversationTitleFromPrompt(titleSource);
            if (!string.IsNullOrWhiteSpace(title))
            {
                active.Title = title;
                RenderConversationTabs();
            }
        }

        private static bool IsUntitledConversation(string title)
        {
            string normalized = (title ?? string.Empty).Trim();
            return normalized.Length == 0
                || string.Equals(normalized, "会话", StringComparison.OrdinalIgnoreCase)
                || string.Equals(normalized, "新会话", StringComparison.OrdinalIgnoreCase);
        }

        private static string BuildConversationTitleFromPrompt(string prompt)
        {
            string value = (prompt ?? string.Empty).Trim();
            if (value.Length == 0)
            {
                return string.Empty;
            }

            char[] separators = { '\r', '\n', '，', ',', '。', '.', '；', ';', '：', ':', '！', '!', '？', '?' };
            int cut = value.IndexOfAny(separators);
            if (cut > 0)
            {
                value = value.Substring(0, cut).Trim();
            }

            value = Regex.Replace(value, @"\s+", "");
            if (value.Length > 10)
            {
                value = value.Substring(0, 10);
            }

            return value;
        }

        private void ConversationTab_Click(object sender, RoutedEventArgs e)
        {
            Button button = sender as Button;
            SwitchConversation(button != null ? button.Tag as string : string.Empty);
        }

        private void CloseConversationTab_Click(object sender, RoutedEventArgs e)
        {
            e.Handled = true;
            Button button = sender as Button;
            CloseConversation(button != null ? button.Tag as string : string.Empty);
        }

        private void CloseConversation(string sessionId)
        {
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                return;
            }

            SaveActiveConversationMessages();
            int index = _conversationSessions.FindIndex(item => item != null && string.Equals(item.Id, sessionId, StringComparison.OrdinalIgnoreCase));
            if (index < 0)
            {
                return;
            }

            bool closingActive = string.Equals(_activeConversationId, sessionId, StringComparison.OrdinalIgnoreCase);
            _conversationSessions.RemoveAt(index);
            if (_conversationSessions.Count == 0)
            {
                _activeConversationId = string.Empty;
                _conversationSequence = 0;
                CreateConversationTab();
                return;
            }

            if (closingActive)
            {
                int nextIndex = Math.Min(index, _conversationSessions.Count - 1);
                _activeConversationId = _conversationSessions[nextIndex].Id;
                MessageList.Children.Clear();
                List<UIElement> children = _conversationSessions[nextIndex].MessageChildren ?? new List<UIElement>();
                for (int i = 0; i < children.Count; i++)
                {
                    MessageList.Children.Add(children[i]);
                }
                ClearTaskStepper();
                ClearTaskCenter();
            }

            RenderConversationTabs();
            RefreshMessageBubbleWidths();
            MessageScroller.ScrollToEnd();
        }

        public void FocusInput()
        {
            FocusInputBox(true);
        }

        private MessageBubbleHandle AddPendingAssistantBubble()
        {
            MessageBubbleHandle handle = null;
            Dispatcher.Invoke(() =>
            {
                handle = AppendMessageBubble("assistant", BuildThinkingText());
                handle.IsThinking = true;
                RefreshMessageExtras(handle.MessageStack, "assistant", string.Empty, isThinking: true);
                _activeThinkingBubble = handle;
                _thinkingFrame = 0;
                StartThinkingIndicator();
            });
            return handle;
        }

        private MessageBubbleHandle AppendMessageBubble(string role, string content)
        {
            TextBox contentText;
            Border bubble = CreateMessageBubble(role, content, out contentText);
            StackPanel messageStack = new StackPanel
            {
                HorizontalAlignment = bubble.HorizontalAlignment
            };
            messageStack.Children.Add(bubble);
            Border shell = new Border
            {
                Child = messageStack,
                Margin = new Thickness(0, 0, 0, 10)
            };

            MessageList.Children.Add(shell);
            RefreshMessageExtras(messageStack, role, content, isThinking: false);
            RefreshMessageBubbleWidths();
            MessageScroller.ScrollToEnd();
            return new MessageBubbleHandle
            {
                Shell = shell,
                MessageStack = messageStack,
                Bubble = bubble,
                ContentText = contentText
            };
        }

        private string GetPlannerTaskId(DrawCommandResponse response)
        {
            if (response != null && !string.IsNullOrWhiteSpace(response.PlannerSessionId))
            {
                return response.PlannerSessionId.Trim();
            }

            return _llmClient != null ? (_llmClient.GetCurrentPlannerSessionId() ?? string.Empty).Trim() : string.Empty;
        }

        private void PreviewModifyParameters_Click(object sender, RoutedEventArgs e)
        {
            SetStatus("等待补充约束");
            InputBox.Focus();
            if (string.IsNullOrWhiteSpace(InputBox.Text))
            {
                InputBox.Text = "需要修改：";
                InputBox.CaretIndex = InputBox.Text.Length;
            }
        }

        private Border BuildParameterRequestPanel(DrawCommandResponse response, Thickness margin)
        {
            string taskId = GetPlannerTaskId(response);
            string hint = BuildParameterRequestHint(response);
            string skillId = ResolvePrimarySelectedSkillId(response);
            SkillDefinitionResponse cachedSkill = GetCachedSkillDefinition(skillId);
            SkillParameterDefinitionResponse[] activeParameter = { ResolvePrimarySkillParameter(cachedSkill) };
            TextBox parameterBox = new TextBox
            {
                Margin = new Thickness(0, 8, 0, 0),
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#1E1E1E")),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#3A3D41")),
                BorderThickness = new Thickness(1),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F3F3F3")),
                CaretBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#58A6FF")),
                Padding = new Thickness(10, 7, 10, 7),
                FontSize = 12,
                MinHeight = 34,
                Text = string.Empty,
                ToolTip = BuildParameterToolTip(activeParameter[0])
            };

            StackPanel content = new StackPanel();
            Grid header = BuildPlannerPanelHeader("补充参数", "待补充", "#463A18", "#D7BA7D", "#FFE6A3");
            content.Children.Add(header);
            TextBlock fieldLabel = new TextBlock
            {
                Text = BuildParameterFieldLabel(activeParameter[0]),
                Margin = new Thickness(0, 8, 0, 0),
                FontSize = 10.5,
                FontWeight = FontWeights.SemiBold,
                TextWrapping = TextWrapping.Wrap,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#DDE6EC"))
            };
            content.Children.Add(fieldLabel);
            content.Children.Add(parameterBox);

            WrapPanel suggestions = new WrapPanel
            {
                Margin = new Thickness(0, 8, 0, 0)
            };
            PopulateParameterSuggestions(suggestions, parameterBox, activeParameter[0]);
            content.Children.Add(suggestions);

            TextBlock hintBlock = new TextBlock
            {
                Text = hint,
                Margin = new Thickness(0, 6, 0, 0),
                FontSize = 10.5,
                TextWrapping = TextWrapping.Wrap,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#A5ADB7"))
            };
            Expander hintExpander = new Expander
            {
                Header = "查看说明",
                Margin = new Thickness(0, 6, 0, 0),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#C8CDD4")),
                Content = hintBlock
            };
            content.Children.Add(hintExpander);

            StackPanel actions = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 10, 0, 0)
            };

            Button continueButton = new Button
            {
                Content = "继续",
                Style = (Style)FindResource("PrimaryButtonStyle"),
                MinWidth = 62,
                IsEnabled = !string.IsNullOrWhiteSpace(taskId)
            };
            continueButton.Click += async (sender, args) =>
            {
                string value = (parameterBox.Text ?? string.Empty).Trim();
                if (string.IsNullOrWhiteSpace(value))
                {
                    SetStatus("请先填写" + BuildParameterStatusLabel(activeParameter[0]));
                    parameterBox.Focus();
                    return;
                }

                await ResumeParameterRequestAsync(taskId, BuildParameterResumeMessage(activeParameter[0], value));
            };
            actions.Children.Add(continueButton);

            if (!string.IsNullOrWhiteSpace(taskId))
            {
                Button cancelButton = CreateRecentTaskButton("取消任务", "cancel", taskId, false);
                cancelButton.Margin = new Thickness(8, 0, 0, 0);
                actions.Children.Add(cancelButton);
            }

            content.Children.Add(actions);

            Border shell = BuildPlannerPanelShell(content, margin, "#201A10", "#8A6F2A");
            if (!string.IsNullOrWhiteSpace(skillId) && cachedSkill == null)
            {
                _ = LoadAndApplySkillParameterMetadataAsync(skillId, activeParameter, header, fieldLabel, hintBlock, parameterBox, suggestions);
            }

            return shell;
        }

        private Button CreateParameterSuggestionChip(string label, TextBox targetBox)
        {
            Button chip = new Button
            {
                Content = label,
                Style = (Style)FindResource("TopActionButtonStyle"),
                Margin = new Thickness(0, 0, 6, 6),
                Padding = new Thickness(8, 3, 8, 3),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#414852")),
                BorderThickness = new Thickness(1),
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#1C2024"))
            };
            chip.Click += (sender, args) =>
            {
                targetBox.Text = label;
                targetBox.Focus();
                targetBox.SelectAll();
            };
            return chip;
        }

        private SkillDefinitionResponse GetCachedSkillDefinition(string skillId)
        {
            string normalized = (skillId ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(normalized))
            {
                return null;
            }

            SkillDefinitionResponse skill;
            return _skillDefinitionCache.TryGetValue(normalized, out skill) ? skill : null;
        }

        private async Task LoadAndApplySkillParameterMetadataAsync(
            string skillId,
            SkillParameterDefinitionResponse[] activeParameter,
            Grid header,
            TextBlock fieldLabel,
            TextBlock hintBlock,
            TextBox parameterBox,
            WrapPanel suggestions)
        {
            try
            {
                if (_llmClient == null || string.IsNullOrWhiteSpace(skillId))
                {
                    return;
                }

                SkillDefinitionResponse skill = await _llmClient.GetPlannerSkillAsync(skillId);
                if (skill == null)
                {
                    return;
                }

                _skillDefinitionCache[skillId.Trim()] = skill;
                SkillParameterDefinitionResponse parameter = ResolvePrimarySkillParameter(skill);
                if (parameter == null)
                {
                    return;
                }

                Action apply = () =>
                {
                    activeParameter[0] = parameter;
                    UpdateParameterHeaderTitle(header, parameter);
                    if (fieldLabel != null)
                    {
                        fieldLabel.Text = BuildParameterFieldLabel(parameter);
                    }
                    parameterBox.ToolTip = BuildParameterToolTip(parameter);
                    hintBlock.Text = BuildParameterMetadataHint(hintBlock.Text, parameter);
                    PopulateParameterSuggestions(suggestions, parameterBox, parameter);
                };

                if (Dispatcher.CheckAccess())
                {
                    apply();
                }
                else
                {
                    Dispatcher.Invoke(apply);
                }
            }
            catch (Exception ex)
            {
                Logger.Error("Failed to load planner skill metadata: " + ex.Message);
            }
        }

        private static void UpdateParameterHeaderTitle(Grid header, SkillParameterDefinitionResponse parameter)
        {
            if (header == null || header.Children == null || header.Children.Count == 0)
            {
                return;
            }

            TextBlock titleText = header.Children[0] as TextBlock;
            if (titleText != null)
            {
                titleText.Text = BuildParameterPanelTitle(parameter);
            }
        }

        private static SkillParameterDefinitionResponse ResolvePrimarySkillParameter(SkillDefinitionResponse skill)
        {
            if (skill == null || skill.Parameters == null || skill.Parameters.Count == 0)
            {
                return null;
            }

            for (int i = 0; i < skill.Parameters.Count; i++)
            {
                SkillParameterDefinitionResponse parameter = skill.Parameters[i];
                if (parameter != null && parameter.Required)
                {
                    return parameter;
                }
            }

            return skill.Parameters[0];
        }

        private static string ResolvePrimarySelectedSkillId(DrawCommandResponse response)
        {
            List<string> selectedSkills = null;
            if (response != null && response.PlannerState != null && response.PlannerState.SelectedSkills != null)
            {
                selectedSkills = response.PlannerState.SelectedSkills;
            }
            else if (response != null)
            {
                selectedSkills = response.SelectedSkills;
            }

            if (selectedSkills == null)
            {
                return string.Empty;
            }

            for (int i = 0; i < selectedSkills.Count; i++)
            {
                string skillId = (selectedSkills[i] ?? string.Empty).Trim();
                if (!string.IsNullOrWhiteSpace(skillId))
                {
                    return skillId;
                }
            }

            return string.Empty;
        }

        private void PopulateParameterSuggestions(WrapPanel suggestions, TextBox targetBox, SkillParameterDefinitionResponse parameter)
        {
            suggestions.Children.Clear();
            List<string> options = parameter != null && parameter.Options != null ? parameter.Options : null;
            if (options != null)
            {
                for (int i = 0; i < options.Count; i++)
                {
                    string option = (options[i] ?? string.Empty).Trim();
                    if (!string.IsNullOrWhiteSpace(option))
                    {
                        suggestions.Children.Add(CreateParameterSuggestionChip(option, targetBox));
                    }
                }
            }

            if (suggestions.Children.Count == 0 && parameter != null && !string.IsNullOrWhiteSpace(parameter.DefaultValue))
            {
                suggestions.Children.Add(CreateParameterSuggestionChip(parameter.DefaultValue.Trim(), targetBox));
            }

            if (suggestions.Children.Count == 0)
            {
                suggestions.Children.Add(CreateParameterSuggestionChip("WALL", targetBox));
                suggestions.Children.Add(CreateParameterSuggestionChip("TEXT", targetBox));
                suggestions.Children.Add(CreateParameterSuggestionChip("DIM", targetBox));
                suggestions.Children.Add(CreateParameterSuggestionChip("AI_GEOMETRY", targetBox));
            }
        }

        private static string BuildParameterPanelTitle(SkillParameterDefinitionResponse parameter)
        {
            string label = BuildParameterStatusLabel(parameter);
            return string.IsNullOrWhiteSpace(label) ? "还需要一个信息" : "还需要：" + label;
        }

        private static string BuildParameterFieldLabel(SkillParameterDefinitionResponse parameter)
        {
            string label = BuildParameterStatusLabel(parameter);
            string valueType = parameter != null && !string.IsNullOrWhiteSpace(parameter.ValueType)
                ? parameter.ValueType.Trim()
                : "string";
            string required = parameter == null || parameter.Required ? "必填" : "可选";
            return label + " · " + required + " · " + valueType;
        }

        private static string BuildParameterStatusLabel(SkillParameterDefinitionResponse parameter)
        {
            if (parameter != null && !string.IsNullOrWhiteSpace(parameter.Label))
            {
                return parameter.Label.Trim();
            }

            return "目标图层";
        }

        private static string BuildParameterToolTip(SkillParameterDefinitionResponse parameter)
        {
            if (parameter != null)
            {
                if (!string.IsNullOrWhiteSpace(parameter.Description))
                {
                    return parameter.Description.Trim();
                }

                return "请输入" + BuildParameterStatusLabel(parameter);
            }

            return "输入目标图层名，例如 WALL、TEXT、DIM";
        }

        private static string BuildParameterMetadataHint(string currentHint, SkillParameterDefinitionResponse parameter)
        {
            string hint = (currentHint ?? string.Empty).Trim();
            if (parameter == null || string.IsNullOrWhiteSpace(parameter.Description))
            {
                return hint;
            }

            string description = parameter.Description.Trim();
            if (hint.IndexOf(description, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return hint;
            }

            return string.IsNullOrWhiteSpace(hint) ? description : hint + "\n参数说明：" + description;
        }

        private static string BuildParameterResumeMessage(SkillParameterDefinitionResponse parameter, string value)
        {
            string normalizedValue = (value ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(normalizedValue))
            {
                return string.Empty;
            }

            return BuildParameterStatusLabel(parameter) + "：" + normalizedValue;
        }

        private Border BuildPlannerPreviewCard(DrawCommandResponse response, Thickness margin)
        {
            List<PlannerExecutionEventResponse> previewEvents = GetPlannerPreviewEvents(response);
            string toolNames = BuildPlannerPreviewToolNames(response, previewEvents);
            string nextStep = BuildPlannerPreviewNextStep(response);

            StackPanel content = new StackPanel();
            content.Children.Add(BuildPlannerPanelHeader("准备应用更改", "等待确认", "#2A2D2A", "#454A45", "#D9DEE3"));

            if (!string.IsNullOrWhiteSpace(toolNames))
            {
                content.Children.Add(CreatePlannerPreviewField("将要调用", toolNames.Trim(), true));
            }

            string summary = BuildPlannerPreviewCompactSummary(previewEvents);
            if (!string.IsNullOrWhiteSpace(summary))
            {
                content.Children.Add(CreatePlannerPreviewField("更改预览", summary, true));
            }

            if (string.IsNullOrWhiteSpace(summary) && previewEvents.Count == 0)
            {
                content.Children.Add(CreatePlannerPreviewField("当前状态", "已生成更改预览，尚未修改图纸。", true));
            }

            if (!string.IsNullOrWhiteSpace(nextStep))
            {
                content.Children.Add(CreatePlannerPreviewField("确认后", nextStep, true));
            }

            StackPanel actions = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 10, 0, 0)
            };

            string taskId = GetPlannerTaskId(response);
            if (!string.IsNullOrWhiteSpace(taskId))
            {
                actions.Children.Add(CreateRecentTaskButton("应用到图纸", "confirm", taskId, true));
            }

            Button reviewButton = new Button
            {
                Content = "查看细节",
                Tag = response,
                Style = (Style)FindResource("TopActionButtonStyle"),
                Margin = new Thickness(actions.Children.Count > 0 ? 8 : 0, 0, 0, 0),
                Padding = new Thickness(8, 3, 8, 3)
            };
            reviewButton.Click += ReviewPlannerPreview_Click;
            actions.Children.Add(reviewButton);

            Button modifyButton = new Button
            {
                Content = "调整要求",
                Style = (Style)FindResource("TopActionButtonStyle"),
                Margin = new Thickness(actions.Children.Count > 0 ? 8 : 0, 0, 0, 0),
                Padding = new Thickness(8, 3, 8, 3)
            };
            modifyButton.Click += PreviewModifyParameters_Click;
            actions.Children.Add(modifyButton);
            content.Children.Add(actions);

            Expander details = new Expander
            {
                Header = "技术细节",
                Margin = new Thickness(0, 8, 0, 0),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#C8CDD4")),
                Content = BuildPlannerPreviewDetailsPanel(previewEvents)
            };
            content.Children.Add(details);

            return BuildPlannerPanelShell(content, margin, "#202220", "#3A3D41");
        }

        private Border BuildPlannerProcessCard(DrawCommandResponse response, Thickness margin)
        {
            StackPanel content = new StackPanel();
            string taskStatus = GetPlannerTaskStatus(response);
            string badgeText = BuildPlannerProcessBadgeText(response);
            content.Children.Add(BuildPlannerPanelHeader("任务过程", badgeText, CopilotUiTokens.BadgeBackground, CopilotUiTokens.BadgeBorder, CopilotUiTokens.TextSecondary));

            string summary = BuildPlannerProcessSummary(response);
            if (!string.IsNullOrWhiteSpace(summary))
            {
                content.Children.Add(new TextBlock
                {
                    Text = summary,
                    Margin = new Thickness(0, 8, 0, 0),
                    FontSize = 11.5,
                    TextWrapping = TextWrapping.Wrap,
                    Foreground = CopilotUiTokens.Brush(CopilotUiTokens.TextSecondary)
                });
            }

            string permissionLine = BuildPlannerPermissionLine(response);
            if (!string.IsNullOrWhiteSpace(permissionLine))
            {
                content.Children.Add(new TextBlock
                {
                    Text = permissionLine,
                    Margin = new Thickness(0, 5, 0, 0),
                    FontSize = 10.5,
                    TextWrapping = TextWrapping.Wrap,
                    Foreground = CopilotUiTokens.Brush(CopilotUiTokens.TextMuted)
                });
            }

            StackPanel detailsPanel = new StackPanel { Margin = new Thickness(0, 8, 0, 0) };
            AddPlannerProcessSteps(detailsPanel, response);
            if (!AddPlannerHarnessEvents(detailsPanel, response))
            {
                AddPlannerProcessEvents(detailsPanel, response);
            }

            Expander details = new Expander
            {
                Header = IsPlannerCompleted(response) ? "查看全部过程" : "计划与工具调用",
                IsExpanded = !IsPlannerCompleted(response),
                Margin = new Thickness(0, 8, 0, 0),
                Foreground = CopilotUiTokens.Brush(CopilotUiTokens.TextSecondary),
                Content = detailsPanel
            };
            content.Children.Add(details);

            if (IsPlannerAwaitingWriteConfirmation(response))
            {
                StackPanel actions = new StackPanel
                {
                    Orientation = Orientation.Horizontal,
                    Margin = new Thickness(0, 10, 0, 0),
                    HorizontalAlignment = HorizontalAlignment.Right
                };
                string taskId = GetPlannerTaskId(response);
                if (!string.IsNullOrWhiteSpace(taskId))
                {
                    actions.Children.Add(CreateRecentTaskButton("允许", "confirm", taskId, true));
                    actions.Children.Add(CreateRecentTaskButton("不允许", "deny", taskId, false));
                }
                content.Children.Add(actions);
            }

            return BuildPlannerPanelShell(content, margin, CopilotUiTokens.SurfaceRaised, CopilotUiTokens.Border);
        }

        private static void AddPlannerProcessSteps(StackPanel panel, DrawCommandResponse response)
        {
            List<string> completedSteps = GetPlannerCompletedSteps(response);
            List<string> pendingSteps = GetPlannerPendingSteps(response);
            if (completedSteps.Count == 0 && pendingSteps.Count == 0)
            {
                return;
            }

            panel.Children.Add(CreatePlannerProcessSectionTitle("计划步骤"));
            for (int i = 0; i < completedSteps.Count; i++)
            {
                string step = (completedSteps[i] ?? string.Empty).Trim();
                if (step.Length > 0)
                {
                    panel.Children.Add(CreatePlannerProcessLine("✓", step, CopilotUiTokens.Success));
                }
            }
            for (int i = 0; i < pendingSteps.Count; i++)
            {
                string step = (pendingSteps[i] ?? string.Empty).Trim();
                if (step.Length > 0)
                {
                    panel.Children.Add(CreatePlannerProcessLine(IsPlannerAwaitingWriteConfirmation(response) && i == 0 ? "!" : "○", step, CopilotUiTokens.TextMuted));
                }
            }
        }

        private static void AddPlannerProcessEvents(StackPanel panel, DrawCommandResponse response)
        {
            List<PlannerExecutionEventResponse> events = GetPlannerExecutionEvents(response);
            if (events.Count == 0)
            {
                return;
            }

            panel.Children.Add(CreatePlannerProcessSectionTitle("运行与修改"));
            for (int i = 0; i < events.Count; i++)
            {
                PlannerExecutionEventResponse item = events[i];
                if (item == null)
                {
                    continue;
                }

                bool failed = string.Equals(item.Status, "failed", StringComparison.OrdinalIgnoreCase);
                string marker = failed ? "×" : "✓";
                string color = failed ? CopilotUiTokens.Danger : CopilotUiTokens.Success;
                panel.Children.Add(CreatePlannerProcessLine(marker, BuildPlannerProcessEventText(item), color));
            }
        }

        private static bool AddPlannerHarnessEvents(StackPanel panel, DrawCommandResponse response)
        {
            List<HarnessEventResponse> events = GetPlannerHarnessEvents(response);
            if (events.Count == 0)
            {
                return false;
            }

            panel.Children.Add(CreatePlannerProcessSectionTitle("任务流"));
            for (int i = 0; i < events.Count; i++)
            {
                HarnessEventResponse item = events[i];
                if (item == null || !item.VisibleToUser)
                {
                    continue;
                }

                panel.Children.Add(CreateHarnessEventCard(item));
            }

            return true;
        }

        private static Border CreateHarnessEventCard(HarnessEventResponse item)
        {
            HarnessEventDisplayModel model = HarnessEventDisplayFormatter.Format(item);
            Grid row = new Grid
            {
                Margin = new Thickness(0, 0, 0, 7)
            };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

            Border marker = new Border
            {
                Width = 18,
                Height = 18,
                CornerRadius = new CornerRadius(9),
                Background = CopilotUiTokens.Brush(CopilotUiTokens.Surface),
                BorderBrush = CopilotUiTokens.Brush(ResolveHarnessToneColor(model.Tone)),
                BorderThickness = new Thickness(1),
                VerticalAlignment = VerticalAlignment.Top,
                Child = new TextBlock
                {
                    Text = model.Marker,
                    FontSize = 10,
                    FontWeight = FontWeights.SemiBold,
                    HorizontalAlignment = HorizontalAlignment.Center,
                    VerticalAlignment = VerticalAlignment.Center,
                    Foreground = CopilotUiTokens.Brush(ResolveHarnessToneColor(model.Tone))
                }
            };
            row.Children.Add(marker);

            StackPanel body = new StackPanel();
            TextBlock title = new TextBlock
            {
                Text = model.Title,
                FontSize = 11.2,
                FontWeight = FontWeights.SemiBold,
                TextWrapping = TextWrapping.Wrap,
                Foreground = CopilotUiTokens.Brush(CopilotUiTokens.TextPrimary)
            };
            body.Children.Add(title);

            if (!string.IsNullOrWhiteSpace(model.Summary))
            {
                body.Children.Add(new TextBlock
                {
                    Text = model.Summary,
                    Margin = new Thickness(0, 2, 0, 0),
                    FontSize = 10.6,
                    TextWrapping = TextWrapping.Wrap,
                    Foreground = CopilotUiTokens.Brush(CopilotUiTokens.TextSecondary)
                });
            }

            if (!string.IsNullOrWhiteSpace(model.Detail))
            {
                body.Children.Add(new TextBlock
                {
                    Text = model.Detail,
                    Margin = new Thickness(0, 3, 0, 0),
                    FontSize = 10,
                    TextWrapping = TextWrapping.Wrap,
                    Foreground = CopilotUiTokens.Brush(CopilotUiTokens.TextMuted)
                });
            }

            Grid.SetColumn(body, 1);
            row.Children.Add(body);

            return new Border
            {
                Child = row,
                Margin = new Thickness(0, 0, 0, 6),
                Padding = new Thickness(8, 7, 8, 7),
                BorderBrush = CopilotUiTokens.Brush(CopilotUiTokens.BorderSoft),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(6),
                Background = CopilotUiTokens.Brush(model.CollapseDefault ? CopilotUiTokens.Surface : CopilotUiTokens.SurfaceRaised)
            };
        }

        private static string ResolveHarnessToneColor(string tone)
        {
            switch ((tone ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "danger":
                    return CopilotUiTokens.Danger;
                case "warning":
                    return CopilotUiTokens.Warning;
                case "success":
                    return CopilotUiTokens.Success;
                default:
                    return CopilotUiTokens.TextMuted;
            }
        }

        private static TextBlock CreatePlannerProcessSectionTitle(string text)
        {
            return new TextBlock
            {
                Text = text,
                Margin = new Thickness(0, 8, 0, 4),
                FontSize = 11,
                FontWeight = FontWeights.SemiBold,
                Foreground = CopilotUiTokens.Brush(CopilotUiTokens.TextSecondary)
            };
        }

        private static Grid CreatePlannerProcessLine(string marker, string text, string markerColor)
        {
            Grid row = new Grid { Margin = new Thickness(0, 0, 0, 5) };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row.Children.Add(new TextBlock
            {
                Text = marker,
                Width = 18,
                FontSize = 11,
                Foreground = CopilotUiTokens.Brush(markerColor),
                VerticalAlignment = VerticalAlignment.Top
            });
            TextBlock label = new TextBlock
            {
                Text = text,
                FontSize = 11,
                TextWrapping = TextWrapping.Wrap,
                Foreground = CopilotUiTokens.Brush(CopilotUiTokens.TextMuted)
            };
            Grid.SetColumn(label, 1);
            row.Children.Add(label);
            return row;
        }

        private static string BuildPlannerProcessEventText(PlannerExecutionEventResponse item)
        {
            string toolName = (item.ToolName ?? "tool").Trim();
            if (string.Equals(toolName, "permission_decision", StringComparison.OrdinalIgnoreCase))
            {
                string decision = ReadPlannerPreviewText(item.Details, "decision");
                if (string.Equals(decision, "deny", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(decision, "reject", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(decision, "cancel", StringComparison.OrdinalIgnoreCase))
                {
                    return "用户拒绝写入当前预览。";
                }

                return "已记录用户权限选择。";
            }

            string summary = GetPlannerEventDisplaySummary(item);
            string dryRunSuffix = string.Empty;
            if (item.Details != null)
            {
                bool? dryRun = ReadPlannerPreviewBool(item.Details, "dry_run");
                if (dryRun.HasValue)
                {
                    dryRunSuffix = dryRun.Value ? " · 预览" : " · 已写入";
                }
            }

            if (string.IsNullOrWhiteSpace(summary))
            {
                summary = string.Equals(item.Status, "failed", StringComparison.OrdinalIgnoreCase) ? "执行失败" : "执行完成";
            }

            return toolName + dryRunSuffix + "：" + summary;
        }

        private static string BuildPlannerProcessSummary(DrawCommandResponse response)
        {
            if (IsPlannerAwaitingWriteConfirmation(response))
            {
                return "已生成更改预览，正在等待你允许写入图纸。";
            }
            if (IsPlannerAwaitingSkillParameters(response))
            {
                return "任务需要补充参数，补充后会继续当前计划。";
            }
            if (IsPlannerCompleted(response))
            {
                return "任务已完成。下方可展开查看计划步骤和工具调用记录。";
            }
            if (IsPlannerFailed(response))
            {
                return "任务未完成。下方可展开查看失败位置和工具回执。";
            }
            return "智能体正在根据计划推进任务。";
        }

        private static string BuildPlannerPermissionLine(DrawCommandResponse response)
        {
            string approval = GetAgentApprovalDisplayName(GetPlannerAgentApproval(response));
            string pendingAction = (GetPlannerPendingPermissionAction(response) ?? string.Empty).Trim();
            string summary = (GetPlannerPermissionSummary(response) ?? string.Empty).Trim();

            if (string.IsNullOrWhiteSpace(approval) && string.IsNullOrWhiteSpace(pendingAction) && string.IsNullOrWhiteSpace(summary))
            {
                return string.Empty;
            }

            string actionLabel = string.Empty;
            if (string.Equals(pendingAction, "confirm_write", StringComparison.OrdinalIgnoreCase))
            {
                actionLabel = "待允许写入图纸";
            }
            else if (!string.IsNullOrWhiteSpace(pendingAction))
            {
                actionLabel = "待补充：" + pendingAction;
            }

            if (!string.IsNullOrWhiteSpace(actionLabel))
            {
                return "权限：" + approval + " · " + actionLabel;
            }

            return "权限：" + approval;
        }

        private static string BuildPlannerProcessBadgeText(DrawCommandResponse response)
        {
            if (IsPlannerAwaitingWriteConfirmation(response))
            {
                return "等待允许";
            }
            if (IsPlannerAwaitingSkillParameters(response))
            {
                return "待补充";
            }
            if (IsPlannerCompleted(response))
            {
                return "已完成";
            }
            if (IsPlannerFailed(response))
            {
                return "失败";
            }
            string status = GetPlannerTaskStatus(response);
            return string.IsNullOrWhiteSpace(status) ? "运行中" : BuildTaskStatusLabel(status);
        }

        private Grid BuildPlannerPanelHeader(string title, string badgeText, string badgeBackground, string badgeBorder, string badgeForeground)
        {
            Grid header = new Grid
            {
                Margin = new Thickness(0, 0, 0, 2)
            };
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            header.Children.Add(new TextBlock
            {
                Text = title,
                FontSize = 11.5,
                FontWeight = FontWeights.SemiBold,
                Foreground = CopilotUiTokens.Brush(CopilotUiTokens.TextPrimary)
            });

            Border badge = new Border
            {
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString(badgeBackground)),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(badgeBorder)),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(9),
                Padding = new Thickness(7, 2, 7, 2),
                Child = new TextBlock
                {
                    Text = badgeText,
                    FontSize = 9.8,
                    FontWeight = FontWeights.SemiBold,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString(badgeForeground))
                }
            };
            Grid.SetColumn(badge, 1);
            header.Children.Add(badge);
            return header;
        }

        private Border BuildPlannerPanelShell(UIElement content, Thickness margin, string background, string border)
        {
            return new Border
            {
                Tag = "planner-preview",
                Margin = margin,
                Padding = new Thickness(12, 10, 12, 10),
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString(background)),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(border)),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(8),
                HorizontalAlignment = HorizontalAlignment.Left,
                MaxWidth = CalculateMessageBubbleMaxWidth("planner-preview"),
                Child = content
            };
        }

        private static StackPanel CreatePlannerPreviewField(string label, string value, bool addTopMargin)
        {
            StackPanel field = new StackPanel
            {
                Margin = addTopMargin ? new Thickness(0, 8, 0, 0) : new Thickness(0)
            };
            field.Children.Add(new TextBlock
            {
                Text = label,
                FontSize = 10,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#7FA6BE"))
            });
            field.Children.Add(new TextBlock
            {
                Text = value,
                Margin = new Thickness(0, 2, 0, 0),
                FontSize = 10.8,
                TextWrapping = TextWrapping.Wrap,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#DDE6EC"))
            });
            return field;
        }

        private static string BuildParameterRequestHint(DrawCommandResponse response)
        {
            string hint = GetPlannerAskUserHint(response).Trim();
            if (!string.IsNullOrWhiteSpace(hint))
            {
                return hint;
            }

            return "请选择或输入要整理的目标图层。当前任务会在补齐信息后继续，不会创建新任务。";
        }

        private static string BuildPlannerPreviewCompactSummary(List<PlannerExecutionEventResponse> previewEvents)
        {
            List<string> fragments = new List<string>();
            for (int i = 0; i < previewEvents.Count; i++)
            {
                PlannerExecutionEventResponse previewEvent = previewEvents[i];
                if (previewEvent == null)
                {
                    continue;
                }

                string displaySummary = GetPlannerEventDisplaySummary(previewEvent);
                if (!string.IsNullOrWhiteSpace(displaySummary))
                {
                    fragments.Add(displaySummary);
                    continue;
                }

                string geometryText = BuildPlannerPreviewGeometryText(previewEvent);
                if (!string.IsNullOrWhiteSpace(geometryText))
                {
                    fragments.Add(geometryText);
                }
            }

            if (fragments.Count == 0)
            {
                return "已生成更改预览，尚未修改图纸。";
            }

            return string.Join("；", fragments);
        }

        private static string NormalizePlannerPreviewSummary(string summary)
        {
            return PlannerEventSummaryFormatter.NormalizePreviewSummary(summary);
        }

        private static string GetPlannerEventDisplaySummary(PlannerExecutionEventResponse executionEvent)
        {
            return PlannerEventSummaryFormatter.GetDisplaySummary(executionEvent);
        }

        private static string GetPlannerEventSemanticSummary(PlannerExecutionEventResponse executionEvent)
        {
            return PlannerEventSummaryFormatter.GetSemanticSummary(executionEvent);
        }

        private static bool IsPlannerTechnicalDryRunText(string value)
        {
            return PlannerEventSummaryFormatter.IsTechnicalDryRunText(value);
        }

        private StackPanel BuildPlannerPreviewDetailsPanel(List<PlannerExecutionEventResponse> previewEvents)
        {
            StackPanel details = new StackPanel
            {
                Margin = new Thickness(0, 6, 0, 0)
            };

            if (previewEvents == null || previewEvents.Count == 0)
            {
                details.Children.Add(new TextBlock
                {
                    Text = "暂无更多工具详情。",
                    FontSize = 10,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#8B949E"))
                });
                return details;
            }

            for (int i = 0; i < previewEvents.Count; i++)
            {
                PlannerExecutionEventResponse previewEvent = previewEvents[i];
                if (previewEvent == null)
                {
                    continue;
                }

                StackPanel row = new StackPanel();
                row.Children.Add(new TextBlock
                {
                    Text = string.IsNullOrWhiteSpace(previewEvent.ToolName) ? "Planner 工具" : previewEvent.ToolName.Trim(),
                    FontSize = 10.5,
                    FontWeight = FontWeights.SemiBold,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#DDE6EC"))
                });

                List<string> lines = new List<string>();
                string displaySummary = GetPlannerEventDisplaySummary(previewEvent);
                if (!string.IsNullOrWhiteSpace(displaySummary))
                {
                    lines.Add(displaySummary);
                }

                string detailText = BuildPlannerPreviewEventDetailText(previewEvent);
                if (!string.IsNullOrWhiteSpace(detailText))
                {
                    lines.Add(detailText);
                }

                string geometryText = BuildPlannerPreviewGeometryText(previewEvent);
                if (!string.IsNullOrWhiteSpace(geometryText))
                {
                    lines.Add("预计写入内容: " + geometryText);
                }

                if (!string.IsNullOrWhiteSpace(previewEvent.RequestId))
                {
                    lines.Add("request_id: " + previewEvent.RequestId.Trim());
                }

                if (!string.IsNullOrWhiteSpace(previewEvent.TraceId))
                {
                    lines.Add("trace_id: " + previewEvent.TraceId.Trim());
                }

                row.Children.Add(new TextBlock
                {
                    Text = lines.Count > 0 ? string.Join("\n", lines) : "已生成更改预览，尚未修改图纸。",
                    Margin = new Thickness(0, 3, 0, 0),
                    FontSize = 9.8,
                    TextWrapping = TextWrapping.Wrap,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#A5ADB7"))
                });

                details.Children.Add(new Border
                {
                    Child = row,
                    Margin = new Thickness(0, 6, 0, 0),
                    Padding = new Thickness(8, 7, 8, 7),
                    CornerRadius = new CornerRadius(6),
                    Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#101A21")),
                    BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#274D63")),
                    BorderThickness = new Thickness(1)
                });
            }

            return details;
        }

        private static string BuildPlannerPreviewEventDetailText(PlannerExecutionEventResponse previewEvent)
        {
            JObject details = previewEvent != null ? previewEvent.Details : null;
            if (details == null)
            {
                return string.Empty;
            }

            List<string> fragments = new List<string>();

            bool? dryRun = ReadPlannerPreviewBool(details, "dry_run");
            if (dryRun.GetValueOrDefault())
            {
                fragments.Add("写入前预览");
            }

            int? commandCount = ReadPlannerPreviewInt(details, "command_count");
            if (commandCount.HasValue && commandCount.Value > 0)
            {
                fragments.Add("命令 " + commandCount.Value + " 条");
            }

            int? affectedEntities = ReadPlannerPreviewInt(details, "affected_entities_count");
            if (affectedEntities.HasValue && affectedEntities.Value > 0)
            {
                fragments.Add((dryRun.GetValueOrDefault() ? "预计影响 " : "影响 ") + affectedEntities.Value + " 个图元");
            }

            string layer = ReadPlannerPreviewText(details, "layer");
            if (!string.IsNullOrWhiteSpace(layer))
            {
                fragments.Add("图层 " + layer.Trim());
            }

            int? color = ReadPlannerPreviewInt(details, "color");
            if (color.HasValue)
            {
                fragments.Add("颜色 " + color.Value);
            }

            return string.Join(" · ", fragments);
        }

        private static string BuildPlannerPreviewGeometryText(PlannerExecutionEventResponse previewEvent)
        {
            List<DrawCommand> commands = GetPlannerPreviewCommands(previewEvent);
            if (commands.Count == 0)
            {
                return string.Empty;
            }

            int maxVisible = Math.Min(commands.Count, 3);
            List<string> fragments = new List<string>();
            for (int i = 0; i < maxVisible; i++)
            {
                string summary = BuildPlannerPreviewCommandSummary(commands[i]);
                if (!string.IsNullOrWhiteSpace(summary))
                {
                    fragments.Add(summary);
                }
            }

            if (fragments.Count == 0)
            {
                return string.Empty;
            }

            if (commands.Count > maxVisible)
            {
                fragments.Add("另有 " + (commands.Count - maxVisible) + " 条命令");
            }

            return string.Join("；", fragments);
        }

        private static List<DrawCommand> GetPlannerPreviewCommands(PlannerExecutionEventResponse previewEvent)
        {
            JObject details = previewEvent != null ? previewEvent.Details : null;
            if (details == null)
            {
                return new List<DrawCommand>();
            }

            JToken commandsToken = GetPlannerPreviewToken(details, "commands");
            JArray commandArray = commandsToken as JArray;
            if (commandArray == null || commandArray.Count == 0)
            {
                return new List<DrawCommand>();
            }

            try
            {
                List<DrawCommand> commands = commandArray.ToObject<List<DrawCommand>>();
                return commands ?? new List<DrawCommand>();
            }
            catch
            {
                return new List<DrawCommand>();
            }
        }

        private static List<DrawCommand> GetPlannerPreviewCommands(DrawCommandResponse response)
        {
            List<DrawCommand> commands = new List<DrawCommand>();
            List<PlannerExecutionEventResponse> previewEvents = GetPlannerPreviewEvents(response);
            for (int i = 0; i < previewEvents.Count; i++)
            {
                List<DrawCommand> eventCommands = GetPlannerPreviewCommands(previewEvents[i]);
                for (int j = 0; j < eventCommands.Count; j++)
                {
                    commands.Add(eventCommands[j]);
                }
            }

            return commands;
        }

        private static string BuildPlannerPreviewCommandSummary(DrawCommand command)
        {
            if (command == null)
            {
                return string.Empty;
            }

            string type = (command.Type ?? string.Empty).Trim().ToUpperInvariant();
            string suffix = BuildPlannerPreviewCommandSuffix(command);
            switch (type)
            {
                case "LINE":
                    return "线段 " + FormatPlannerPreviewPoint(command.Start) + " -> " + FormatPlannerPreviewPoint(command.End) + suffix;
                case "RECTANGLE":
                    return "矩形 " + FormatPlannerPreviewPoint(command.Start) + " 到 " + FormatPlannerPreviewPoint(command.End) + suffix;
                case "CIRCLE":
                    return "圆心 " + FormatPlannerPreviewPoint(command.Center) + " 半径 " + FormatPlannerPreviewNumber(command.Radius) + suffix;
                case "TEXT":
                    return "文字 \"" + EllipsizePlannerPreviewText(command.Content, 16) + "\" @ " + FormatPlannerPreviewPoint(command.Position) + suffix;
                case "POLYLINE":
                case "LWPOLYLINE":
                    return "折线 " + GetPlannerPreviewPointCount(command.Points) + " 点" + suffix;
                default:
                    return (type.Length > 0 ? type : "绘图命令") + suffix;
            }
        }

        private static string BuildPlannerPreviewCommandSuffix(DrawCommand command)
        {
            List<string> fragments = new List<string>();
            if (!string.IsNullOrWhiteSpace(command.Layer))
            {
                fragments.Add("图层 " + command.Layer.Trim());
            }

            if (command.Color.HasValue)
            {
                fragments.Add("颜色 " + command.Color.Value);
            }

            return fragments.Count == 0 ? string.Empty : " [" + string.Join("，", fragments) + "]";
        }

        private static string FormatPlannerPreviewPoint(double[] point)
        {
            if (point == null || point.Length < 2)
            {
                return "(?)";
            }

            return "(" + FormatPlannerPreviewNumber(point[0]) + ", " + FormatPlannerPreviewNumber(point[1]) + ")";
        }

        private static string FormatPlannerPreviewNumber(double? value)
        {
            if (!value.HasValue)
            {
                return "?";
            }

            return value.Value.ToString("0.##", CultureInfo.InvariantCulture);
        }

        private static int GetPlannerPreviewPointCount(double[][] points)
        {
            return points != null ? points.Length : 0;
        }

        private static string EllipsizePlannerPreviewText(string value, int maxLength)
        {
            string text = (value ?? string.Empty).Trim();
            if (text.Length <= maxLength)
            {
                return text;
            }

            return text.Substring(0, Math.Max(0, maxLength)) + "...";
        }

        private static bool? ReadPlannerPreviewBool(JObject details, string key)
        {
            JToken token = GetPlannerPreviewToken(details, key);
            bool parsed;
            return token != null && bool.TryParse(token.ToString(), out parsed) ? parsed : (bool?)null;
        }

        private static int? ReadPlannerPreviewInt(JObject details, string key)
        {
            JToken token = GetPlannerPreviewToken(details, key);
            int parsed;
            return token != null && int.TryParse(token.ToString(), out parsed) ? parsed : (int?)null;
        }

        private static string ReadPlannerPreviewText(JObject details, string key)
        {
            JToken token = GetPlannerPreviewToken(details, key);
            return token != null ? (token.ToString() ?? string.Empty).Trim() : string.Empty;
        }

        private static JToken GetPlannerPreviewToken(JObject details, string key)
        {
            if (details == null || string.IsNullOrWhiteSpace(key))
            {
                return null;
            }

            JToken token;
            if (details.TryGetValue(key, StringComparison.OrdinalIgnoreCase, out token))
            {
                return token;
            }

            JObject data = details["data"] as JObject;
            if (data != null && data.TryGetValue(key, StringComparison.OrdinalIgnoreCase, out token))
            {
                return token;
            }

            return null;
        }

        private void UpdateMessageBubble(MessageBubbleHandle handle, string role, string content)
        {
            if (handle == null)
            {
                AddMessage(role, content);
                return;
            }

            Dispatcher.Invoke(() =>
            {
                if (handle == _activeThinkingBubble)
                {
                    StopThinkingIndicator();
                }

                handle.IsThinking = false;
                ApplyMessageBubbleStyle(handle.Bubble, handle.ContentText, role);
                handle.ContentText.Text = content;
                RefreshMessageExtras(handle.MessageStack, role, content, isThinking: false);
                RefreshMessageBubbleWidths();
                MessageScroller.ScrollToEnd();
            });
        }

        private void RefreshMessageExtras(StackPanel messageStack, string role, string content, bool isThinking)
        {
            if (messageStack == null)
            {
                return;
            }

            while (messageStack.Children.Count > 1)
            {
                messageStack.Children.RemoveAt(1);
            }

            if (isThinking || !string.Equals(role, "assistant", StringComparison.OrdinalIgnoreCase))
            {
                return;
            }

            string commandText = ExtractCadCommandText(content);
            if (!string.IsNullOrWhiteSpace(commandText))
            {
                messageStack.Children.Add(CreateCommandCopyPanel(commandText));
            }

            messageStack.Children.Add(CreateMessageActionBar(content));
        }

        private UIElement CreateMessageActionBar(string content)
        {
            StackPanel actionBar = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 6, 0, 0),
                HorizontalAlignment = HorizontalAlignment.Left,
                Opacity = 0.82
            };

            actionBar.Children.Add(CreateInlineActionButton("⧉", "复制", (sender, args) => CopyTextToClipboard(content, "已复制回复内容。")));
            actionBar.Children.Add(CreateInlineActionButton("👍", "赞", (sender, args) => SetStatus("已记录反馈")));
            actionBar.Children.Add(CreateInlineActionButton("👎", "踩", (sender, args) => SetStatus("已记录反馈")));
            actionBar.Children.Add(new TextBlock
            {
                Text = "“ 内容由 AI 生成",
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#7D8590")),
                FontSize = 11,
                Margin = new Thickness(8, 2, 0, 0),
                VerticalAlignment = VerticalAlignment.Center
            });
            return actionBar;
        }

        private UIElement CreateCommandCopyPanel(string commandText)
        {
            Grid grid = new Grid();
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            TextBlock title = new TextBlock
            {
                Text = "CAD 命令",
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#A9B1BA")),
                FontSize = 11,
                Margin = new Thickness(0, 0, 8, 6)
            };
            Grid.SetRow(title, 0);
            Grid.SetColumn(title, 0);
            grid.Children.Add(title);

            Button copyButton = CreateInlineActionButton("复制命令", "复制 CAD 命令", (sender, args) => CopyTextToClipboard(commandText, "已复制 CAD 命令。"));
            Grid.SetRow(copyButton, 0);
            Grid.SetColumn(copyButton, 1);
            grid.Children.Add(copyButton);

            TextBox commandBox = new TextBox
            {
                Text = commandText,
                IsReadOnly = true,
                AcceptsReturn = true,
                TextWrapping = TextWrapping.NoWrap,
                FontFamily = new FontFamily("Consolas"),
                FontSize = 12,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#DCE3DA")),
                Background = Brushes.Transparent,
                BorderThickness = new Thickness(0),
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
                MinHeight = 44,
                MaxHeight = 160
            };
            Grid.SetRow(commandBox, 1);
            Grid.SetColumnSpan(commandBox, 2);
            grid.Children.Add(commandBox);

            return new Border
            {
                Margin = new Thickness(0, 8, 48, 0),
                Padding = new Thickness(10),
                BorderThickness = new Thickness(1),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#343941")),
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#171A1D")),
                CornerRadius = new CornerRadius(6),
                Child = grid
            };
        }

        private Button CreateInlineActionButton(string content, string tooltip, RoutedEventHandler clickHandler)
        {
            Button button = new Button
            {
                Content = content,
                ToolTip = tooltip,
                Background = Brushes.Transparent,
                BorderBrush = Brushes.Transparent,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#8B949E")),
                Padding = new Thickness(4, 1, 4, 1),
                Margin = new Thickness(0, 0, 5, 0),
                FontSize = 12,
                Cursor = Cursors.Hand
            };
            button.Click += clickHandler;
            return button;
        }

        private void CopyTextToClipboard(string text, string successStatus)
        {
            try
            {
                Clipboard.SetText(text ?? string.Empty);
                SetStatus(successStatus);
            }
            catch (Exception ex)
            {
                SetStatus("复制失败: " + ex.Message);
            }
        }

        private static string ExtractCadCommandText(string content)
        {
            if (string.IsNullOrWhiteSpace(content))
            {
                return string.Empty;
            }

            string[] lines = content.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
            List<string> commandLines = new List<string>();
            for (int i = 0; i < lines.Length; i++)
            {
                string line = (lines[i] ?? string.Empty).Trim();
                if (line.Length == 0)
                {
                    continue;
                }

                if (LooksLikeCadCommandLine(line))
                {
                    commandLines.Add(line);
                }
            }

            return commandLines.Count > 0 ? string.Join(Environment.NewLine, commandLines) : string.Empty;
        }

        private static bool LooksLikeCadCommandLine(string line)
        {
            string upper = (line ?? string.Empty).TrimStart().ToUpperInvariant();
            string[] prefixes =
            {
                "CIRCLE ", "LINE ", "RECTANGLE ", "POLYLINE ", "PLINE ", "ARC ",
                "TEXT ", "MTEXT ", "DIMENSION ", "DIM ", "LAYER ", "-LAYER ",
                "OFFSET ", "TRIM ", "EXTEND ", "MOVE ", "COPY ", "ROTATE "
            };

            for (int i = 0; i < prefixes.Length; i++)
            {
                if (upper.StartsWith(prefixes[i], StringComparison.Ordinal))
                {
                    return true;
                }
            }

            return false;
        }

        private void RefreshMessageBubbleWidths()
        {
            if (MessageList == null)
            {
                return;
            }

            Dispatcher.BeginInvoke(new Action(() =>
            {
                for (int i = 0; i < MessageList.Children.Count; i++)
                {
                    Border shell = MessageList.Children[i] as Border;
                    StackPanel messageStack = shell != null ? shell.Child as StackPanel : null;
                    Border bubble = messageStack != null && messageStack.Children.Count > 0
                        ? messageStack.Children[0] as Border
                        : shell != null ? shell.Child as Border : null;
                    if (bubble == null)
                    {
                        continue;
                    }

                    string role = bubble.Tag as string ?? string.Empty;
                    bubble.MaxWidth = CalculateMessageBubbleMaxWidth(role);
                }
            }), DispatcherPriority.Background);
        }

        private double CalculateMessageBubbleMaxWidth(string role)
        {
            double viewportWidth = MessageScroller != null && MessageScroller.ViewportWidth > 0
                ? MessageScroller.ViewportWidth
                : ConversationRegion != null ? ConversationRegion.ActualWidth - 12 : 320;

            double reservedWidth = string.Equals(role, "user", StringComparison.OrdinalIgnoreCase) ? 120 : 72;
            double maxWidth = viewportWidth - reservedWidth;
            return Math.Max(140, maxWidth);
        }

        private void FocusInputBox(bool moveCaretToEnd)
        {
            Dispatcher.BeginInvoke(new Action(() =>
            {
                if (!IsVisible)
                {
                    return;
                }

                InputBox.Focus();
                Keyboard.Focus(InputBox);
                if (moveCaretToEnd)
                {
                    InputBox.CaretIndex = InputBox.Text.Length;
                }
            }), DispatcherPriority.Input);
        }

        private ContextMenu CreateEditableTextContextMenu(TextBox textBox)
        {
            ContextMenu menu = new ContextMenu();

            MenuItem cutItem = new MenuItem { Header = "剪切", Tag = textBox };
            cutItem.Click += EditableCut_Click;
            menu.Items.Add(cutItem);

            MenuItem copyItem = new MenuItem { Header = "复制", Tag = textBox };
            copyItem.Click += EditableCopy_Click;
            menu.Items.Add(copyItem);

            MenuItem pasteItem = new MenuItem { Header = "粘贴", Tag = textBox };
            pasteItem.Click += EditablePaste_Click;
            menu.Items.Add(pasteItem);

            menu.Items.Add(new Separator());

            MenuItem selectAllItem = new MenuItem { Header = "全选", Tag = textBox };
            selectAllItem.Click += EditableSelectAll_Click;
            menu.Items.Add(selectAllItem);

            return menu;
        }

        private ContextMenu CreateReadOnlyTextContextMenu()
        {
            ContextMenu menu = new ContextMenu();

            MenuItem copyItem = new MenuItem { Header = "复制" };
            copyItem.Click += ReadOnlyCopy_Click;
            menu.Items.Add(copyItem);

            MenuItem selectAllItem = new MenuItem { Header = "全选" };
            selectAllItem.Click += ReadOnlySelectAll_Click;
            menu.Items.Add(selectAllItem);

            return menu;
        }

        private void EditableTextBox_PreviewMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
        {
            TextBox textBox = sender as TextBox;
            if (textBox == null)
            {
                return;
            }

            if (!textBox.IsKeyboardFocusWithin)
            {
                textBox.Focus();
                int charIndex = textBox.GetCharacterIndexFromPoint(e.GetPosition(textBox), true);
                if (charIndex >= 0)
                {
                    textBox.CaretIndex = charIndex;
                }
                else
                {
                    textBox.CaretIndex = textBox.Text.Length;
                }

                e.Handled = true;
            }
        }

        private async void EditableTextBox_PreviewKeyDown(object sender, KeyEventArgs e)
        {
            TextBox textBox = sender as TextBox;
            if (textBox == null)
            {
                return;
            }

            if (e.Key == Key.Enter && (Keyboard.Modifiers & ModifierKeys.Shift) == 0)
            {
                e.Handled = true;
                await SendMessage();
                return;
            }

            if (Keyboard.Modifiers != ModifierKeys.Control)
            {
                return;
            }

            if (e.Key == Key.A)
            {
                textBox.SelectAll();
                e.Handled = true;
            }
        }

        private void ReadOnlyTextBox_PreviewMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
        {
            TextBox textBox = sender as TextBox;
            if (textBox == null)
            {
                return;
            }

            if (!textBox.IsKeyboardFocusWithin)
            {
                textBox.Focus();
            }
        }

        private void ReadOnlyTextBox_PreviewKeyDown(object sender, KeyEventArgs e)
        {
            TextBox textBox = sender as TextBox;
            if (textBox == null || Keyboard.Modifiers != ModifierKeys.Control)
            {
                return;
            }

            if (e.Key == Key.A)
            {
                textBox.SelectAll();
                e.Handled = true;
            }
            else if (e.Key == Key.C)
            {
                textBox.Copy();
                e.Handled = true;
            }
        }

        private void EditableCut_Click(object sender, RoutedEventArgs e)
        {
            TextBox textBox = (sender as MenuItem)?.Tag as TextBox;
            if (textBox != null)
            {
                textBox.Cut();
            }
        }

        private void EditableCopy_Click(object sender, RoutedEventArgs e)
        {
            TextBox textBox = (sender as MenuItem)?.Tag as TextBox;
            if (textBox != null)
            {
                textBox.Copy();
            }
        }

        private void EditablePaste_Click(object sender, RoutedEventArgs e)
        {
            TextBox textBox = (sender as MenuItem)?.Tag as TextBox;
            if (textBox != null)
            {
                textBox.Paste();
            }
        }

        private void EditableSelectAll_Click(object sender, RoutedEventArgs e)
        {
            TextBox textBox = (sender as MenuItem)?.Tag as TextBox;
            if (textBox != null)
            {
                textBox.SelectAll();
            }
        }

        private void ReadOnlyCopy_Click(object sender, RoutedEventArgs e)
        {
            TextBox textBox = ((sender as MenuItem)?.Parent as ContextMenu)?.PlacementTarget as TextBox;
            if (textBox != null)
            {
                textBox.Copy();
            }
        }

        private void ReadOnlySelectAll_Click(object sender, RoutedEventArgs e)
        {
            TextBox textBox = ((sender as MenuItem)?.Parent as ContextMenu)?.PlacementTarget as TextBox;
            if (textBox != null)
            {
                textBox.SelectAll();
            }
        }

        private void StartThinkingIndicator()
        {
            if (!_thinkingIndicatorTimer.IsEnabled)
            {
                _thinkingIndicatorTimer.Start();
            }
        }

        private void StopThinkingIndicator()
        {
            _thinkingIndicatorTimer.Stop();
            _activeThinkingBubble = null;
            _thinkingFrame = 0;
        }

        private void ThinkingIndicatorTimer_Tick(object sender, EventArgs e)
        {
            if (_activeThinkingBubble == null || !_activeThinkingBubble.IsThinking)
            {
                StopThinkingIndicator();
                return;
            }

            _thinkingFrame = (_thinkingFrame + 1) % 4;
            _activeThinkingBubble.ContentText.Text = BuildThinkingText();
        }

        private string BuildThinkingText()
        {
            return "正在思考" + new string('.', _thinkingFrame);
        }

        private static string BuildUserPreviewText(string text, string attachmentKind, string attachmentName)
        {
            StringBuilder builder = new StringBuilder();
            if (!string.IsNullOrWhiteSpace(text))
            {
                builder.Append(text.Trim());
            }

            if (!string.IsNullOrWhiteSpace(attachmentName))
            {
                if (builder.Length > 0)
                {
                    builder.AppendLine();
                    builder.AppendLine();
                }

                builder.Append("已附");
                builder.Append(string.IsNullOrWhiteSpace(attachmentKind) ? "附件" : attachmentKind);
                builder.Append("：");
                builder.Append(attachmentName);
            }

            return builder.Length == 0 ? "已发送空白消息。" : builder.ToString();
        }

        private static string BuildRequestText(string userText, string attachmentKind, string attachmentName, string attachmentText, string attachmentMeta)
        {
            StringBuilder builder = new StringBuilder((userText ?? string.Empty).Trim());

            if (!string.IsNullOrWhiteSpace(attachmentText))
            {
                if (builder.Length > 0)
                {
                    builder.AppendLine();
                    builder.AppendLine();
                }

                builder.Append("以下是用户附带的");
                builder.Append(string.IsNullOrWhiteSpace(attachmentKind) ? "文件" : attachmentKind);
                builder.Append("内容，文件名为 ");
                builder.Append(attachmentName);
                builder.AppendLine("。请结合其中信息理解需求，并在回复中引用必要内容。");
                if (!string.IsNullOrWhiteSpace(attachmentMeta))
                {
                    builder.Append("附件说明：");
                    builder.AppendLine(attachmentMeta);
                }

                builder.AppendLine("附件正文：");
                builder.Append(attachmentText);
            }

            return builder.ToString();
        }

        private async Task<List<string>> BuildTaskPlanAsync(string userText, string attachmentKind, string attachmentName, string attachmentText)
        {
            try
            {
                StringBuilder prompt = new StringBuilder();
                prompt.AppendLine("请将下面这个 CAD 助手任务拆解为 3 到 5 个简短步骤。要求：");
                prompt.AppendLine("1. 每行一个步骤。");
                prompt.AppendLine("2. 不要编号。");
                prompt.AppendLine("3. 每步控制在 8 到 18 个中文字符。");
                prompt.AppendLine("4. 只输出步骤本身，不要解释。");
                prompt.AppendLine();
                prompt.AppendLine("任务内容：");
                prompt.AppendLine(string.IsNullOrWhiteSpace(userText) ? "用户发送了一个仅含附件的请求。" : userText.Trim());

                if (!string.IsNullOrWhiteSpace(attachmentName))
                {
                    prompt.AppendLine();
                    prompt.Append("附件：");
                    prompt.Append(string.IsNullOrWhiteSpace(attachmentKind) ? "附件" : attachmentKind);
                    prompt.Append(" - ");
                    prompt.AppendLine(attachmentName);
                }

                if (!string.IsNullOrWhiteSpace(attachmentText))
                {
                    prompt.AppendLine();
                    prompt.AppendLine("附件正文存在，请在拆解步骤中考虑阅读与提取关键信息。");
                }

                string response = await _llmClient.Chat(prompt.ToString(), null);
                List<string> steps = ParseTaskPlan(response);
                return steps.Count > 0 ? steps : BuildFallbackPlan(attachmentName, attachmentText);
            }
            catch
            {
                return BuildFallbackPlan(attachmentName, attachmentText);
            }
        }

        private StepTrackerHandle AddTaskStepper(List<string> steps)
        {
            List<string> effectiveSteps = steps != null && steps.Count > 0 ? steps : BuildFallbackPlan(null, null);

            StepTrackerHandle tracker = new StepTrackerHandle();

            Grid layout = new Grid();
            layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

            Grid headerGrid = new Grid
            {
                Cursor = Cursors.Hand,
                Margin = new Thickness(0, 0, 0, 2)
            };
            headerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            headerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            headerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            TextBlock collapseGlyph = new TextBlock
            {
                Text = "▾",
                FontSize = 12,
                Margin = new Thickness(0, 0, 8, 0),
                VerticalAlignment = VerticalAlignment.Center,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#D9DEE3"))
            };
            headerGrid.Children.Add(collapseGlyph);

            TextBlock title = new TextBlock
            {
                Text = "待办事项(0/" + effectiveSteps.Count + ")",
                FontSize = 11,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#D9DEE3")),
                VerticalAlignment = VerticalAlignment.Center
            };
            Grid.SetColumn(title, 1);
            headerGrid.Children.Add(title);

            TextBlock toggleGlyph = new TextBlock
            {
                Text = "☰",
                FontSize = 11,
                Margin = new Thickness(8, 0, 0, 0),
                VerticalAlignment = VerticalAlignment.Center,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#8B949E"))
            };
            Grid.SetColumn(toggleGlyph, 2);
            headerGrid.Children.Add(toggleGlyph);
            Grid.SetRow(headerGrid, 0);
            layout.Children.Add(headerGrid);

            StackPanel bodyPanel = new StackPanel { Margin = new Thickness(0, 8, 0, 0) };

            List<TextBlock> markers = new List<TextBlock>();
            List<TextBlock> items = new List<TextBlock>();

            for (int i = 0; i < effectiveSteps.Count; i++)
            {
                Grid row = new Grid { Margin = new Thickness(0, 0, 0, 6) };
                row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

                TextBlock marker = new TextBlock
                {
                    Text = i == 0 ? "◔" : "○",
                    FontSize = 11,
                    Width = 18,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString(i == 0 ? "#D7BA7D" : "#7F8893")),
                    VerticalAlignment = VerticalAlignment.Top
                };

                TextBlock label = new TextBlock
                {
                    Text = effectiveSteps[i],
                    FontSize = 11,
                    TextWrapping = TextWrapping.Wrap,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString(i == 0 ? "#F1F3F5" : "#A5ADB7"))
                };

                Grid.SetColumn(marker, 0);
                Grid.SetColumn(label, 1);
                row.Children.Add(marker);
                row.Children.Add(label);
                bodyPanel.Children.Add(row);
                markers.Add(marker);
                items.Add(label);
            }

            Grid.SetRow(bodyPanel, 1);
            layout.Children.Add(bodyPanel);

            Border container = new Border
            {
                Child = layout,
                Cursor = Cursors.Hand,
                Tag = tracker
            };
            container.MouseLeftButtonUp += TaskStepperContainer_MouseLeftButtonUp;

            tracker.Container = container;
            tracker.BodyPanel = bodyPanel;
            tracker.CollapseGlyphText = collapseGlyph;
            tracker.ToggleGlyphText = toggleGlyph;
            tracker.TitleText = title;
            tracker.MarkerTexts = markers;
            tracker.ItemTexts = items;

            TaskProgressHost.Content = container;
            TaskProgressRegion.Visibility = Visibility.Visible;
            MessageScroller.ScrollToEnd();

            return tracker;
        }

        private void UpdateTaskStepper(StepTrackerHandle tracker, int completedCount)
        {
            if (tracker == null || tracker.ItemTexts == null || tracker.MarkerTexts == null)
            {
                return;
            }

            int total = tracker.ItemTexts.Count;
            int safeCompleted = Math.Max(0, Math.Min(completedCount, total));
            for (int i = 0; i < total; i++)
            {
                bool isComplete = i < safeCompleted;
                bool isActive = i == safeCompleted && safeCompleted < total;

                tracker.MarkerTexts[i].Text = isComplete ? "✓" : isActive ? "◔" : "○";
                tracker.MarkerTexts[i].Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString(isComplete ? "#4EC9B0" : isActive ? "#D7BA7D" : "#7F8893"));
                tracker.ItemTexts[i].Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString(isComplete ? "#D9F4EA" : isActive ? "#F1F3F5" : "#A5ADB7"));
            }

            tracker.TitleText.Text = "待办事项(" + safeCompleted + "/" + total + ")";
            MessageScroller.ScrollToEnd();
        }

        private void ClearTaskStepper()
        {
            TaskProgressHost.Content = null;
            TaskProgressRegion.Visibility = Visibility.Collapsed;
        }

        private void ClearTaskCenter()
        {
            if (TaskCenterHost != null)
            {
                TaskCenterHost.Content = null;
            }

            if (TaskCenterDrawer != null)
            {
                TaskCenterDrawer.Visibility = Visibility.Collapsed;
            }
        }

        private void ClearDiagnosticsPanel()
        {
            if (DiagnosticsHost != null)
            {
                DiagnosticsHost.Content = null;
            }

            if (DiagnosticsDrawer != null)
            {
                DiagnosticsDrawer.Visibility = Visibility.Collapsed;
            }
        }

        private void ClearReviewPanel()
        {
            if (ReviewHost != null)
            {
                ReviewHost.Content = null;
            }

            if (ReviewDrawer != null)
            {
                ReviewDrawer.Visibility = Visibility.Collapsed;
            }
        }

        private void ClearContextPanel()
        {
            if (ContextHost != null)
            {
                ContextHost.Content = null;
            }

            if (ContextDrawer != null)
            {
                ContextDrawer.Visibility = Visibility.Collapsed;
            }
        }

        private void ShowContextPanel()
        {
            try
            {
                DrawingContextService.DrawingContextSummary summary = DrawingContextService.GetUiSummary();
                RenderContextPanel(summary);
                SetStatus("上下文已更新");
            }
            catch (Exception ex)
            {
                Logger.Error("Failed to render drawing context: " + ex.Message);
                StackPanel layout = new StackPanel();
                layout.Children.Add(CreatePanelTitle("上下文", "读取失败"));
                layout.Children.Add(new TextBlock
                {
                    Text = ex.Message,
                    Margin = new Thickness(0, 8, 0, 0),
                    FontSize = 11,
                    TextWrapping = TextWrapping.Wrap,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F48771"))
                });
                ContextHost.Content = layout;
                ContextDrawer.Visibility = Visibility.Visible;
                SetStatus("上下文读取失败");
            }
        }

        private void RenderContextPanel(DrawingContextService.DrawingContextSummary summary)
        {
            StackPanel layout = new StackPanel();
            layout.Children.Add(CreatePanelTitle("上下文", "当前图纸"));

            if (summary == null)
            {
                layout.Children.Add(new TextBlock
                {
                    Text = "当前没有可用图纸上下文。",
                    Margin = new Thickness(0, 8, 0, 0),
                    FontSize = 11,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#A5ADB7"))
                });
                ContextHost.Content = layout;
                ContextDrawer.Visibility = Visibility.Visible;
                return;
            }

            layout.Children.Add(CreatePlannerPreviewField("图纸", summary.DocumentName ?? "未命名图纸", true));
            layout.Children.Add(CreatePlannerPreviewField(
                "统计",
                "图层 " + summary.LayerCount.ToString(CultureInfo.InvariantCulture) +
                " · 对象 " + summary.EntityCount.ToString(CultureInfo.InvariantCulture) +
                " · 上下文 " + summary.JsonSize.ToString(CultureInfo.InvariantCulture) + " bytes",
                true));
            layout.Children.Add(CreatePlannerPreviewField(
                "最近变更",
                "命令 " + (summary.LastCommandName ?? "无") + " / " + (summary.LastCommandState ?? "idle") +
                " · 新增 " + summary.AppendedSinceRefresh.ToString(CultureInfo.InvariantCulture) +
                " · 修改 " + summary.ModifiedSinceRefresh.ToString(CultureInfo.InvariantCulture) +
                " · 删除 " + summary.ErasedSinceRefresh.ToString(CultureInfo.InvariantCulture),
                true));
            layout.Children.Add(CreatePlannerPreviewField(
                "时间",
                "变更 " + (summary.LastChangeText ?? "未记录") + " · 刷新 " + (summary.SnapshotRefreshText ?? "未记录"),
                true));
            layout.Children.Add(CreatePlannerPreviewField("选择集", PrettyJsonForPanel(summary.SelectionSummaryJson), true));

            Expander snapshotDetails = new Expander
            {
                Header = "图纸摘要片段",
                Margin = new Thickness(0, 10, 0, 0),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#C8CDD4")),
                Content = new TextBox
                {
                    Text = PrettyJsonForPanel(summary.SnapshotPreviewJson),
                    IsReadOnly = true,
                    TextWrapping = TextWrapping.Wrap,
                    AcceptsReturn = true,
                    BorderThickness = new Thickness(0),
                    Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#1E1E1E")),
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#A5ADB7")),
                    FontSize = 10.5,
                    MaxHeight = 180,
                    VerticalScrollBarVisibility = ScrollBarVisibility.Auto
                }
            };
            layout.Children.Add(snapshotDetails);

            StackPanel actions = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 12, 0, 0)
            };
            Button refreshButton = CreateDiagnosticsButton("刷新", false);
            refreshButton.Click += (sender, args) => ShowContextPanel();
            actions.Children.Add(refreshButton);

            Button copyButton = CreateDiagnosticsButton("复制上下文", true);
            copyButton.Tag = summary;
            copyButton.Click += CopyContextSummary_Click;
            actions.Children.Add(copyButton);
            layout.Children.Add(actions);

            ContextHost.Content = layout;
            ContextDrawer.Visibility = Visibility.Visible;
        }

        private void CopyContextSummary_Click(object sender, RoutedEventArgs e)
        {
            DrawingContextService.DrawingContextSummary summary = (sender as FrameworkElement)?.Tag as DrawingContextService.DrawingContextSummary;
            if (summary == null)
            {
                return;
            }

            Clipboard.SetText(BuildContextClipboardText(summary));
            SetStatus("上下文已复制");
        }

        private async Task ShowReviewPanelAsync()
        {
            DrawCommandResponse snapshot = _lastReviewSnapshot;
            if (snapshot == null || !HasPlannerPreview(snapshot))
            {
                snapshot = await TryLoadCurrentReviewSnapshotAsync();
            }

            if (snapshot == null || !HasPlannerPreview(snapshot))
            {
                AddMessage("system", "当前没有可查看的更改预览。请先运行一个需要应用到图纸的智能体任务。");
                SetStatus("暂无更改预览");
                return;
            }

            RenderReviewPanel(snapshot);
        }

        private async Task<DrawCommandResponse> TryLoadCurrentReviewSnapshotAsync()
        {
            if (_llmClient == null)
            {
                return null;
            }

            string taskId = _llmClient.GetCurrentPlannerSessionId();
            if (string.IsNullOrWhiteSpace(taskId))
            {
                return null;
            }

            try
            {
                PlannerTaskDetailResponse detail = await _llmClient.GetPlannerTaskDetailAsync(taskId);
                DrawCommandResponse snapshot = CreatePlannerSnapshot(detail);
                if (HasPlannerPreview(snapshot))
                {
                    RememberReviewSnapshot(snapshot);
                    return snapshot;
                }
            }
            catch (Exception ex)
            {
                Logger.Error("Failed to load review snapshot: " + ex.Message);
            }

            return null;
        }

        private void RenderReviewPanel(DrawCommandResponse response)
        {
            if (response == null)
            {
                return;
            }

            RememberReviewSnapshot(response);

            ConfigDrawer.Visibility = Visibility.Collapsed;
            if (TaskCenterDrawer != null)
            {
                TaskCenterDrawer.Visibility = Visibility.Collapsed;
            }

            if (DiagnosticsDrawer != null)
            {
                DiagnosticsDrawer.Visibility = Visibility.Collapsed;
            }

            List<PlannerExecutionEventResponse> previewEvents = GetPlannerPreviewEvents(response);
            string toolNames = BuildPlannerPreviewToolNames(response, previewEvents);
            string summary = BuildPlannerPreviewCompactSummary(previewEvents);
            string nextStep = BuildPlannerPreviewNextStep(response);
            string taskId = GetPlannerTaskId(response);

            StackPanel layout = new StackPanel();
            layout.Children.Add(CreatePanelTitle("更改预览", "等待应用"));

            layout.Children.Add(new TextBlock
            {
                Text = "这些更改还没有写入图纸。确认后会在当前 AutoCAD 图纸中应用。",
                Margin = new Thickness(0, 8, 0, 0),
                FontSize = 11,
                TextWrapping = TextWrapping.Wrap,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#D9DEE3"))
            });

            if (!string.IsNullOrWhiteSpace(taskId))
            {
                layout.Children.Add(CreatePlannerPreviewField("任务", taskId.Trim(), true));
            }

            if (!string.IsNullOrWhiteSpace(toolNames))
            {
                layout.Children.Add(CreatePlannerPreviewField("将要调用", toolNames.Trim(), true));
            }

            if (!string.IsNullOrWhiteSpace(summary))
            {
                layout.Children.Add(CreatePlannerPreviewField("更改预览", summary.Trim(), true));
            }

            if (!string.IsNullOrWhiteSpace(nextStep))
            {
                layout.Children.Add(CreatePlannerPreviewField("确认后", nextStep.Trim(), true));
            }

            Expander details = new Expander
            {
                Header = "工具与几何详情",
                Margin = new Thickness(0, 10, 0, 0),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#C8CDD4")),
                Content = BuildPlannerPreviewDetailsPanel(previewEvents)
            };
            layout.Children.Add(details);

            StackPanel actions = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 12, 0, 0)
            };
            if (!string.IsNullOrWhiteSpace(taskId))
            {
                actions.Children.Add(CreateRecentTaskButton("应用到图纸", "confirm", taskId, true));
            }

            Button modifyButton = new Button
            {
                Content = "调整要求",
                Style = (Style)FindResource("TopActionButtonStyle"),
                Margin = new Thickness(actions.Children.Count > 0 ? 8 : 0, 0, 0, 0),
                Padding = new Thickness(8, 3, 8, 3)
            };
            modifyButton.Click += PreviewModifyParameters_Click;
            actions.Children.Add(modifyButton);

            Button closeButton = new Button
            {
                Content = "关闭",
                Style = (Style)FindResource("TopActionButtonStyle"),
                Margin = new Thickness(8, 0, 0, 0),
                Padding = new Thickness(8, 3, 8, 3)
            };
            closeButton.Click += (sender, args) => ClearReviewPanel();
            actions.Children.Add(closeButton);
            layout.Children.Add(actions);

            ReviewHost.Content = layout;
            ReviewDrawer.Visibility = Visibility.Visible;
            SetStatus("等待审查确认");
        }

        private void ReviewPlannerPreview_Click(object sender, RoutedEventArgs e)
        {
            DrawCommandResponse response = (sender as FrameworkElement)?.Tag as DrawCommandResponse;
            if (response == null)
            {
                response = _lastReviewSnapshot;
            }

            if (response == null || !HasPlannerPreview(response))
            {
                AddMessage("system", "当前没有可查看的更改预览。");
                return;
            }

            RenderReviewPanel(response);
        }

        private void RememberReviewSnapshot(DrawCommandResponse response)
        {
            if (response != null && HasPlannerPreview(response))
            {
                _lastReviewSnapshot = response;
            }
        }

        private async Task ShowDiagnosticsPanelAsync()
        {
            if (!UseServiceMode() || _llmClient == null)
            {
                AddMessage("system", "诊断报告当前仅在智能体模式下可用。");
                return;
            }

            try
            {
                SetStatus("加载诊断报告");
                DiagnosticsHost.Content = BuildDiagnosticsLoadingPanel();
                DiagnosticsDrawer.Visibility = Visibility.Visible;

                JObject diagnostics = await _llmClient.GetConnectorDiagnosticsAsync();
                RenderConnectorHealthPanel(diagnostics);
                SetStatus(diagnostics != null ? "连接诊断已更新" : "连接诊断为空");
            }
            catch (Exception ex)
            {
                SetStatus("诊断报告加载失败");
                AddMessage("error", "读取诊断报告失败: " + ex.Message);
                DiagnosticsHost.Content = BuildDiagnosticsErrorPanel(ex.Message);
                DiagnosticsDrawer.Visibility = Visibility.Visible;
            }
        }

        private UIElement BuildDiagnosticsLoadingPanel()
        {
            return new TextBlock
            {
                Text = "正在读取诊断报告...",
                FontSize = 11,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#A5ADB7"))
            };
        }

        private UIElement BuildDiagnosticsErrorPanel(string message)
        {
            StackPanel layout = new StackPanel();
            layout.Children.Add(CreatePanelTitle("诊断报告", "读取失败"));
            layout.Children.Add(new TextBlock
            {
                Text = string.IsNullOrWhiteSpace(message) ? "诊断报告读取失败。" : message,
                Margin = new Thickness(0, 8, 0, 0),
                FontSize = 11,
                TextWrapping = TextWrapping.Wrap,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F48771"))
            });
            return layout;
        }

        private void RenderConnectorHealthPanel(JObject health)
        {
            string status = health != null ? (health.Value<string>("status") ?? "ok") : "unknown";
            JArray components = health != null ? health["components"] as JArray : null;
            string componentSummary = components != null
                ? string.Join(
                    Environment.NewLine,
                    components
                        .OfType<JObject>()
                        .Select(item =>
                            string.Format(
                                CultureInfo.InvariantCulture,
                                "{0}: {1} — {2}",
                                item.Value<string>("name") ?? item.Value<string>("id") ?? "unknown",
                                item.Value<string>("status") ?? "unknown",
                                item.Value<string>("summary") ?? string.Empty)))
                : "无响应";
            StackPanel layout = new StackPanel();
            layout.Children.Add(CreatePanelTitle("连接诊断", BuildDiagnosticsStatusLabel(status)));
            layout.Children.Add(CreatePlannerPreviewField("连接方式", GetConnectionModeDisplayName(GetSelectedConnectionMode()), true));
            layout.Children.Add(CreatePlannerPreviewField(
                "服务地址",
                string.IsNullOrWhiteSpace(Config.Get("CADCOPILOT_API_BASE_URL", string.Empty))
                    ? "未配置"
                    : Config.Get("CADCOPILOT_API_BASE_URL", string.Empty),
                true));
            layout.Children.Add(CreatePlannerPreviewField("模型提供商", GetProviderDisplayName(GetSelectedProvider()), true));
            layout.Children.Add(CreatePlannerPreviewField("当前模型", GetCurrentUiModel(), true));
            layout.Children.Add(CreatePlannerPreviewField("五层状态", componentSummary, true));
            layout.Children.Add(CreatePlannerPreviewField(
                "诊断原始数据",
                health != null ? health.ToString(Formatting.Indented) : "无响应",
                true));

            StackPanel actions = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 10, 0, 0)
            };
            Button refreshButton = CreateDiagnosticsButton("刷新", false);
            refreshButton.Click += async (sender, args) => await ShowDiagnosticsPanelAsync();
            actions.Children.Add(refreshButton);

            Button copyButton = CreateDiagnosticsButton("复制", true);
            copyButton.Click += (sender, args) =>
            {
                Clipboard.SetText(health != null ? health.ToString(Formatting.Indented) : "无响应");
                SetStatus("连接诊断已复制");
            };
            actions.Children.Add(copyButton);
            layout.Children.Add(actions);

            DiagnosticsHost.Content = layout;
            DiagnosticsDrawer.Visibility = Visibility.Visible;
        }

        private UIElement CreatePanelTitle(string titleText, string metaText)
        {
            Grid header = new Grid { Margin = new Thickness(0, 0, 0, 2) };
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            header.Children.Add(new TextBlock
            {
                Text = titleText,
                FontSize = 11,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#D9DEE3"))
            });
            TextBlock meta = new TextBlock
            {
                Text = metaText ?? string.Empty,
                FontSize = 10.5,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#8B949E")),
                VerticalAlignment = VerticalAlignment.Center
            };
            Grid.SetColumn(meta, 1);
            header.Children.Add(meta);
            return header;
        }

        private static string BuildDiagnosticsStatusLabel(string status)
        {
            switch ((status ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "ok":
                case "healthy":
                case "passed":
                    return "正常";
                case "degraded":
                case "warning":
                    return "需关注";
                case "failed":
                case "error":
                    return "失败";
                default:
                    return string.IsNullOrWhiteSpace(status) ? "未知" : status.Trim();
            }
        }

        private Button CreateDiagnosticsButton(string label, bool primary)
        {
            Button button = new Button
            {
                Content = label,
                Margin = new Thickness(0, 0, 6, 0),
                Padding = new Thickness(8, 3, 8, 3),
                MinWidth = 54,
                Cursor = Cursors.Hand,
                Style = (Style)FindResource(primary ? "PrimaryButtonStyle" : "TopActionButtonStyle")
            };
            return button;
        }
        private static string BuildContextClipboardText(DrawingContextService.DrawingContextSummary summary)
        {
            if (summary == null)
            {
                return string.Empty;
            }

            StringBuilder builder = new StringBuilder();
            builder.AppendLine("AgentBridge 上下文摘要");
            builder.AppendLine("图纸：" + (summary.DocumentName ?? "未命名图纸"));
            builder.AppendLine("图层：" + summary.LayerCount.ToString(CultureInfo.InvariantCulture));
            builder.AppendLine("对象：" + summary.EntityCount.ToString(CultureInfo.InvariantCulture));
            builder.AppendLine("最近命令：" + (summary.LastCommandName ?? "无") + " / " + (summary.LastCommandState ?? "idle"));
            builder.AppendLine("最近变更：新增 " + summary.AppendedSinceRefresh.ToString(CultureInfo.InvariantCulture) +
                "，修改 " + summary.ModifiedSinceRefresh.ToString(CultureInfo.InvariantCulture) +
                "，删除 " + summary.ErasedSinceRefresh.ToString(CultureInfo.InvariantCulture));
            builder.AppendLine("最近变更时间：" + (summary.LastChangeText ?? "未记录"));
            builder.AppendLine("上下文刷新时间：" + (summary.SnapshotRefreshText ?? "未记录"));
            builder.AppendLine();
            builder.AppendLine("选择集：");
            builder.AppendLine(PrettyJsonForPanel(summary.SelectionSummaryJson));
            builder.AppendLine();
            builder.AppendLine("图纸摘要片段：");
            builder.AppendLine(PrettyJsonForPanel(summary.SnapshotPreviewJson));
            return builder.ToString().Trim();
        }

        private static string PrettyJsonForPanel(string value)
        {
            string normalized = (value ?? string.Empty).Trim();
            if (normalized.Length == 0)
            {
                return "{}";
            }

            try
            {
                return JToken.Parse(normalized).ToString(Formatting.Indented);
            }
            catch
            {
                return normalized;
            }
        }

        private async Task ShowRecentTasksPanelAsync(string filterOverride = null, string selectedTaskIdOverride = null)
        {
            if (!UseServiceMode() || _llmClient == null)
            {
                RenderLightweightHistoryPanel("当前暂无远端历史。智能体模式会同步最近的 Planner 任务记录。");
                CloseWorkSurfaceDrawers(TaskCenterDrawer);
                TaskCenterDrawer.Visibility = Visibility.Visible;
                SetStatus("历史记录");
                return;
            }

            try
            {
                if (!string.IsNullOrWhiteSpace(filterOverride))
                {
                    _taskPanelFilter = filterOverride.Trim().ToLowerInvariant();
                }

                if (selectedTaskIdOverride != null)
                {
                    _taskPanelSelectedTaskId = (selectedTaskIdOverride ?? string.Empty).Trim();
                }

                SetStatus("加载最近任务");
                string serverFilter = NormalizeTaskPanelFilter(_taskPanelFilter);
                List<PlannerTaskSummaryResponse> filteredTasks = await _llmClient.ListRecentPlannerTasksAsync(12, serverFilter);
                PlannerTaskDetailResponse selectedDetail = null;
                if (!string.IsNullOrWhiteSpace(_taskPanelSelectedTaskId))
                {
                    bool selectedVisible = filteredTasks.Exists(task => string.Equals(task.TaskId, _taskPanelSelectedTaskId, StringComparison.OrdinalIgnoreCase));
                    if (selectedVisible)
                    {
                        selectedDetail = await _llmClient.GetPlannerTaskDetailAsync(_taskPanelSelectedTaskId);
                    }
                    else
                    {
                        _taskPanelSelectedTaskId = string.Empty;
                    }
                }

                RenderRecentTasksPanel(filteredTasks, selectedDetail);
                SetStatus(filteredTasks.Count > 0 ? "最近任务已更新" : "暂无匹配任务");
            }
            catch (Exception ex)
            {
                SetStatus("任务列表加载失败");
                AddMessage("error", "读取最近任务失败: " + ex.Message);
            }
        }

        private void RenderLightweightHistoryPanel(string message)
        {
            StackPanel panel = new StackPanel();
            TextBlock title = new TextBlock
            {
                Text = "历史记录",
                FontSize = 12,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#E3E7EB"))
            };
            panel.Children.Add(title);

            TextBlock hint = new TextBlock
            {
                Text = message,
                Margin = new Thickness(0, 8, 0, 0),
                FontSize = 11,
                TextWrapping = TextWrapping.Wrap,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#A9B1BA"))
            };
            panel.Children.Add(hint);

            TaskCenterHost.Content = panel;
        }

        private void RenderRecentTasksPanel(List<PlannerTaskSummaryResponse> tasks, PlannerTaskDetailResponse selectedDetail)
        {
            StackPanel layout = new StackPanel();

            Grid header = new Grid { Margin = new Thickness(0, 0, 0, 10) };
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            TextBlock title = new TextBlock
            {
                Text = "最近任务",
                FontSize = 11,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#D9DEE3"))
            };
            header.Children.Add(title);

            Button refreshButton = new Button
            {
                Content = "刷新",
                Tag = new PlannerTaskActionContext { Action = "refresh" },
                Style = (Style)FindResource("TopActionButtonStyle"),
                Padding = new Thickness(6, 2, 6, 2),
                Margin = new Thickness(8, 0, 0, 0)
            };
            refreshButton.Click += RecentTaskAction_Click;
            Grid.SetColumn(refreshButton, 1);
            header.Children.Add(refreshButton);
            layout.Children.Add(header);
            layout.Children.Add(BuildRecentTaskFilterBar());

            if (selectedDetail != null)
            {
                layout.Children.Add(BuildSelectedTaskDetailCard(selectedDetail));
            }

            if (tasks == null || tasks.Count == 0)
            {
                layout.Children.Add(new TextBlock
                {
                    Text = "当前没有匹配当前筛选条件的任务。",
                    FontSize = 11,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#A5ADB7"))
                });
            }
            else
            {
                for (int i = 0; i < tasks.Count; i++)
                {
                    layout.Children.Add(BuildRecentTaskCard(tasks[i]));
                }
            }

            Border container = new Border
            {
                Child = layout
            };

            TaskCenterHost.Content = container;
            TaskCenterDrawer.Visibility = Visibility.Visible;
        }

        private UIElement BuildRecentTaskFilterBar()
        {
            StackPanel filters = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 0, 0, 10)
            };

            filters.Children.Add(CreateRecentTaskButton("全部", "filter", null, string.Equals(_taskPanelFilter, "all", StringComparison.OrdinalIgnoreCase), "all"));
            filters.Children.Add(CreateRecentTaskButton("待补充", "filter", null, string.Equals(_taskPanelFilter, "waiting_user", StringComparison.OrdinalIgnoreCase), "waiting_user"));
            filters.Children.Add(CreateRecentTaskButton("失败", "filter", null, string.Equals(_taskPanelFilter, "failed", StringComparison.OrdinalIgnoreCase), "failed"));
            filters.Children.Add(CreateRecentTaskButton("已完成", "filter", null, string.Equals(_taskPanelFilter, "completed", StringComparison.OrdinalIgnoreCase), "completed"));
            filters.Children.Add(CreateRecentTaskButton("进行中", "filter", null, string.Equals(_taskPanelFilter, "active", StringComparison.OrdinalIgnoreCase), "active"));

            return filters;
        }

        private Border BuildSelectedTaskDetailCard(PlannerTaskDetailResponse detail)
        {
            StackPanel card = new StackPanel();

            card.Children.Add(new TextBlock
            {
                Text = "当前查看任务",
                FontSize = 10.5,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#8B949E"))
            });
            card.Children.Add(new TextBlock
            {
                Text = string.IsNullOrWhiteSpace(detail.UserGoal) ? "未命名任务" : detail.UserGoal,
                Margin = new Thickness(0, 3, 0, 0),
                FontSize = 11.5,
                FontWeight = FontWeights.SemiBold,
                TextWrapping = TextWrapping.Wrap,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F1F3F5"))
            });

            string meta = BuildTaskDetailMeta(detail);
            if (!string.IsNullOrWhiteSpace(meta))
            {
                card.Children.Add(new TextBlock
                {
                    Text = meta,
                    Margin = new Thickness(0, 4, 0, 0),
                    FontSize = 10.5,
                    TextWrapping = TextWrapping.Wrap,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#A5ADB7"))
                });
            }

            string summary = BuildSelectedTaskSummary(detail);
            if (!string.IsNullOrWhiteSpace(summary))
            {
                card.Children.Add(new TextBlock
                {
                    Text = summary,
                    Margin = new Thickness(0, 6, 0, 0),
                    FontSize = 10.5,
                    TextWrapping = TextWrapping.Wrap,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#D9DEE3"))
                });
            }

            if (IsPlannerAwaitingWriteConfirmation(detail))
            {
                card.Children.Add(BuildPlannerPreviewCard(CreatePlannerSnapshot(detail), new Thickness(0, 8, 0, 0)));
            }

            StackPanel actions = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 8, 0, 0)
            };
            actions.Children.Add(CreateRecentTaskButton("打开", "open", detail.TaskId, false));
            if (detail.Resumable)
            {
                actions.Children.Add(CreateRecentTaskButton("继续", "continue", detail.TaskId, true));
            }
            else if (detail.Retryable)
            {
                actions.Children.Add(CreateRecentTaskButton("重试", "retry", detail.TaskId, true));
            }

            if (detail.Cancellable)
            {
                actions.Children.Add(CreateRecentTaskButton("取消", "cancel", detail.TaskId, false));
            }
            if (string.Equals(detail.TaskStatus, "completed", StringComparison.OrdinalIgnoreCase))
            {
                actions.Children.Add(CreateRecentTaskButton("转为 Skill", "skill-draft", detail.TaskId, false));
            }

            if (detail.Resumable && IsPlannerAwaitingWriteConfirmation(detail))
            {
                actions.Children.Clear();
                actions.Children.Add(CreateRecentTaskButton("应用到图纸", "confirm", detail.TaskId, true));
                if (detail.Cancellable)
                {
                    actions.Children.Add(CreateRecentTaskButton("取消", "cancel", detail.TaskId, false));
                }
            }

            card.Children.Add(actions);

            return new Border
            {
                Child = card,
                Margin = new Thickness(0, 0, 0, 10),
                Padding = new Thickness(10, 8, 10, 8),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#3A3D41")),
                BorderThickness = new Thickness(1),
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#202220"))
            };
        }

        private Border BuildRecentTaskCard(PlannerTaskSummaryResponse task)
        {
            StackPanel card = new StackPanel();

            card.Children.Add(new TextBlock
            {
                Text = string.IsNullOrWhiteSpace(task.UserGoal) ? "未命名任务" : task.UserGoal,
                FontSize = 11,
                FontWeight = FontWeights.SemiBold,
                TextWrapping = TextWrapping.Wrap,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#F1F3F5"))
            });

            string meta = BuildRecentTaskMeta(task);
            if (!string.IsNullOrWhiteSpace(meta))
            {
                card.Children.Add(new TextBlock
                {
                    Text = meta,
                    Margin = new Thickness(0, 4, 0, 0),
                    FontSize = 10.5,
                    TextWrapping = TextWrapping.Wrap,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#A5ADB7"))
                });
            }

            StackPanel actions = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 8, 0, 0)
            };

            actions.Children.Add(CreateRecentTaskButton("打开", "open", task.TaskId, false));
            if (task.Resumable)
            {
                actions.Children.Add(CreateRecentTaskButton("继续", "continue", task.TaskId, true));
            }
            else if (task.Retryable)
            {
                actions.Children.Add(CreateRecentTaskButton("重试", "retry", task.TaskId, true));
            }

            if (task.Cancellable)
            {
                actions.Children.Add(CreateRecentTaskButton("取消", "cancel", task.TaskId, false));
            }
            if (string.Equals(task.TaskStatus, "completed", StringComparison.OrdinalIgnoreCase))
            {
                actions.Children.Add(CreateRecentTaskButton("转为 Skill", "skill-draft", task.TaskId, false));
            }

            card.Children.Add(actions);

            return new Border
            {
                Child = card,
                Margin = new Thickness(0, 0, 0, 8),
                Padding = new Thickness(10, 8, 10, 8),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#323438")),
                BorderThickness = new Thickness(1),
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#1E1E1E"))
            };
        }

        private Button CreateRecentTaskButton(string label, string action, string taskId, bool primary, string value = null)
        {
            Button button = new Button
            {
                Content = label,
                Tag = new PlannerTaskActionContext { Action = action, TaskId = taskId, Value = value },
                Margin = new Thickness(0, 0, 6, 0),
                Padding = new Thickness(8, 3, 8, 3),
                MinWidth = 46,
                Cursor = Cursors.Hand
            };

            if (primary)
            {
                button.Style = (Style)FindResource("PrimaryButtonStyle");
                button.Height = 24;
            }
            else
            {
                button.Style = (Style)FindResource("TopActionButtonStyle");
            }

            button.Click += RecentTaskAction_Click;
            return button;
        }

        private async void RecentTaskAction_Click(object sender, RoutedEventArgs e)
        {
            PlannerTaskActionContext context = (sender as FrameworkElement)?.Tag as PlannerTaskActionContext;
            if (context == null)
            {
                return;
            }

            if (string.Equals(context.Action, "refresh", StringComparison.OrdinalIgnoreCase))
            {
                await ShowRecentTasksPanelAsync();
                return;
            }

            if (string.Equals(context.Action, "filter", StringComparison.OrdinalIgnoreCase))
            {
                await ShowRecentTasksPanelAsync(context.Value, string.Empty);
                return;
            }

            if (string.IsNullOrWhiteSpace(context.TaskId) || _llmClient == null)
            {
                return;
            }

            try
            {
                switch ((context.Action ?? string.Empty).Trim().ToLowerInvariant())
                {
                    case "open":
                        await OpenPlannerTaskAsync(context.TaskId, false);
                        break;
                    case "continue":
                        await OpenPlannerTaskAsync(context.TaskId, true);
                        break;
                    case "confirm":
                        await ConfirmPlannerTaskAsync(context.TaskId);
                        break;
                    case "deny":
                        await DenyPlannerTaskPermissionAsync(context.TaskId);
                        break;
                    case "retry":
                        await RetryPlannerTaskAsync(context.TaskId);
                        break;
                    case "cancel":
                        await CancelPlannerTaskAsync(context.TaskId);
                        break;
                    case "skill-draft":
                        await CreateSkillDraftFromTaskAsync(context.TaskId);
                        break;
                }
            }
            catch (Exception ex)
            {
                SetStatus("任务操作失败");
                AddMessage("error", "任务操作失败: " + ex.Message);
            }
        }

        private async Task OpenPlannerTaskAsync(string taskId, bool armSession)
        {
            SetStatus(armSession ? "接管任务中" : "读取任务中");
            PlannerTaskDetailResponse detail = await _llmClient.GetPlannerTaskDetailAsync(taskId);
            if (detail == null)
            {
                AddMessage("system", "未找到对应任务，可能已经失效。");
                return;
            }

            if (armSession)
            {
                _llmClient.SetCurrentPlannerSessionId(detail.TaskId);
            }
            _taskPanelSelectedTaskId = detail.TaskId ?? string.Empty;

            DrawCommandResponse snapshot = CreatePlannerSnapshot(detail);
            await ApplyHarnessEventsAsync(detail.TaskId, snapshot);
            DisplayPlannerTaskSnapshot(snapshot, true);
            await ShowRecentTasksPanelAsync(null, detail.TaskId);
            AddPlannerProcessPanel(snapshot);
            AddPlannerActionPanel(snapshot);
            AddMessage("system", BuildTaskOpenHint(detail, armSession));
            SetStatus(armSession ? "已切换到当前任务" : "任务详情已加载");
            FocusInputBox(true);
        }

        private async Task RetryPlannerTaskAsync(string taskId)
        {
            SetStatus("重试任务中");
            DrawCommandResponse response = await _llmClient.RetryPlannerTaskAsync(taskId);
            if (response == null)
            {
                AddMessage("system", "当前任务不可重试。");
                return;
            }

            DrawCommandResponse snapshot = await TryRefreshPlannerTaskSnapshotAsync(response);
            DisplayPlannerTaskSnapshot(snapshot, false);
            AddMessage("assistant", BuildPlannerReplyFallback(snapshot));
            AddPlannerProcessPanel(snapshot);
            if (IsPlannerWaitingUser(snapshot))
            {
                AddPlannerActionPanel(snapshot);
                AddMessage("system", BuildPlannerFollowUpHint(snapshot));
                SetStatus(IsPlannerAwaitingWriteConfirmation(snapshot) ? "等待应用到图纸" : "任务等待补充信息");
            }
            else if (IsPlannerFailed(snapshot))
            {
                AddMessage("system", BuildPlannerFailureHint(snapshot));
                SetStatus("任务重试失败");
            }
            else if (IsPlannerCompleted(snapshot))
            {
                AddMessage("system", BuildPlannerCompletionHint(snapshot));
                SetStatus("任务重试完成");
            }
            else
            {
                AddMessage("system", BuildPlannerExecutionEventSummary(GetPlannerExecutionEvents(snapshot)));
                SetStatus("任务重试已开始");
            }

            _taskPanelSelectedTaskId = !string.IsNullOrWhiteSpace(snapshot.PlannerSessionId) ? snapshot.PlannerSessionId : taskId;
            await RefreshTaskCenterIfOpenAsync(_taskPanelSelectedTaskId);
            FocusInputBox(true);
        }

        private async Task CreateSkillDraftFromTaskAsync(string taskId)
        {
            SetStatus("正在生成 Skill 草稿");
            SkillDraftResponse draft = await _llmClient.CreateSkillDraftFromTaskAsync(taskId);
            if (draft == null)
            {
                AddMessage("system", "未能生成 Skill 草稿。");
                SetStatus("Skill 草稿生成失败");
                return;
            }

            AddMessage(
                "system",
                "已生成待审核 Skill 草稿「" + (draft.Name ?? draft.SkillId ?? "未命名") +
                "」。草稿不会自动启用，审核工具范围和步骤后才能发布。");
            SetStatus("Skill 草稿已生成");
            await RefreshTaskCenterIfOpenAsync(taskId);
        }

        private async Task ConfirmPlannerTaskAsync(string taskId)
        {
            PlannerTaskDetailResponse pendingDetail = await _llmClient.GetPlannerTaskDetailAsync(taskId);
            DrawCommandResponse pendingSnapshot = CreatePlannerSnapshot(pendingDetail);
            List<DrawCommand> localCommands = GetPlannerPreviewCommands(pendingSnapshot);
            if (localCommands.Count > 0)
            {
                int executedCount = 0;
                await MainThreadDispatcher.InvokeAsync(() =>
                {
                    executedCount = CommandExecutor.Execute(localCommands);
                });

                ClearReviewPanel();
                _lastReviewSnapshot = null;
                DrawCommandResponse completedSnapshot = await BuildSyncedLocalCompletionSnapshotAsync(taskId, pendingSnapshot, executedCount);
                DisplayPlannerTaskSnapshot(completedSnapshot, false);
                AddMessage("assistant", "已应用到当前图纸。");
                AddPlannerProcessPanel(completedSnapshot);
                AddMessage("system", "完成：已绘制 " + executedCount.ToString(CultureInfo.InvariantCulture) + " 个图元。");
                SetStatus("已应用到图纸");
                _taskPanelSelectedTaskId = !string.IsNullOrWhiteSpace(completedSnapshot.PlannerSessionId)
                    ? completedSnapshot.PlannerSessionId
                    : taskId;
                await RefreshTaskCenterIfOpenAsync(_taskPanelSelectedTaskId);
                FocusInputBox(true);
                return;
            }

            SetStatus("正在应用到图纸");
            DrawCommandResponse response = await _llmClient.ResumePlannerTaskAsync(taskId, "确认执行");
            if (response == null)
            {
                AddMessage("system", "当前任务暂时无法应用到图纸。");
                return;
            }

            DrawCommandResponse snapshot = await TryRefreshPlannerTaskSnapshotAsync(response);
            DisplayPlannerTaskSnapshot(snapshot, false);
            AddMessage("assistant", BuildPlannerReplyFallback(snapshot));
            AddPlannerProcessPanel(snapshot);
            if (IsPlannerWaitingUser(snapshot))
            {
                RememberReviewSnapshot(snapshot);
                AddPlannerActionPanel(snapshot);
                AddMessage("system", BuildPlannerFollowUpHint(snapshot));
                SetStatus(IsPlannerAwaitingWriteConfirmation(snapshot) ? "等待应用到图纸" : "任务等待补充信息");
            }
            else if (IsPlannerFailed(snapshot))
            {
                ClearReviewPanel();
                _lastReviewSnapshot = null;
                AddMessage("system", BuildPlannerFailureHint(snapshot));
                SetStatus("应用到图纸失败");
            }
            else if (IsPlannerCompleted(snapshot))
            {
                ClearReviewPanel();
                _lastReviewSnapshot = null;
                AddMessage("system", BuildPlannerCompletionHint(snapshot));
                SetStatus("已应用到图纸");
            }
            else
            {
                ClearReviewPanel();
                AddMessage("system", BuildPlannerExecutionEventSummary(GetPlannerExecutionEvents(snapshot)));
                SetStatus("已开始应用到图纸");
            }

            _taskPanelSelectedTaskId = !string.IsNullOrWhiteSpace(snapshot.PlannerSessionId) ? snapshot.PlannerSessionId : taskId;
            await RefreshTaskCenterIfOpenAsync(_taskPanelSelectedTaskId);
            FocusInputBox(true);
        }

        private static DrawCommandResponse BuildLocalCompletionSnapshot(DrawCommandResponse source, int executedCount)
        {
            DrawCommandResponse snapshot = source ?? new DrawCommandResponse();
            List<string> completedSteps = new List<string>();
            List<string> originalCompleted = GetPlannerCompletedSteps(snapshot);
            List<string> originalPending = GetPlannerPendingSteps(snapshot);
            for (int i = 0; i < originalCompleted.Count; i++)
            {
                string step = (originalCompleted[i] ?? string.Empty).Trim();
                if (step.Length > 0 && !completedSteps.Contains(step))
                {
                    completedSteps.Add(step);
                }
            }
            for (int i = 0; i < originalPending.Count; i++)
            {
                string step = (originalPending[i] ?? string.Empty).Trim();
                if (step.Length > 0 && !completedSteps.Contains(step))
                {
                    completedSteps.Add(step);
                }
            }
            if (completedSteps.Count == 0)
            {
                completedSteps.Add("生成预览");
                completedSteps.Add("本地确认写入");
            }

            List<string> executedTools = GetPlannerExecutedTools(snapshot);
            if (!executedTools.Contains("local_apply_preview"))
            {
                executedTools.Add("local_apply_preview");
            }

            List<PlannerExecutionEventResponse> events = GetPlannerExecutionEvents(snapshot);
            events.Add(new PlannerExecutionEventResponse
            {
                ToolName = "local_apply_preview",
                Status = "succeeded",
                Summary = "本地 AutoCAD 已应用预览命令",
                TraceId = snapshot.TraceId,
                Details = JObject.FromObject(new
                {
                    dry_run = false,
                    affected_entities_count = executedCount,
                    audit = new
                    {
                        task_id = snapshot.PlannerSessionId,
                        trace_id = snapshot.TraceId,
                        tool_name = "local_apply_preview",
                        side_effect_level = "high",
                        dry_run = false,
                        confirmation_required = false,
                        confirmed_by_local_user = true,
                        write_actor = "local_autocad_plugin"
                    }
                })
            });

            snapshot.TaskStatus = "completed";
            snapshot.AskUserType = string.Empty;
            snapshot.AskUserHint = string.Empty;
            snapshot.Resumable = false;
            snapshot.Retryable = false;
            snapshot.Cancellable = false;
            snapshot.ExecutedTools = executedTools;
            snapshot.ExecutionEvents = events;
            snapshot.PlannerCompletedSteps = completedSteps;
            snapshot.PlannerPendingSteps = new List<string>();
            snapshot.ReplyText = "已应用到当前图纸。";

            if (snapshot.PlannerState == null)
            {
                snapshot.PlannerState = new PlannerStateResponse();
            }
            snapshot.PlannerState.TraceId = snapshot.TraceId;
            snapshot.PlannerState.TaskStatus = "completed";
            snapshot.PlannerState.ExecutedTools = executedTools;
            snapshot.PlannerState.ExecutionEvents = events;
            snapshot.PlannerState.CompletedSteps = completedSteps;
            snapshot.PlannerState.PendingSteps = new List<string>();
            snapshot.PlannerState.AskUserType = string.Empty;
            snapshot.PlannerState.AskUserHint = string.Empty;
            return snapshot;
        }

        private async Task<DrawCommandResponse> BuildSyncedLocalCompletionSnapshotAsync(string taskId, DrawCommandResponse pendingSnapshot, int executedCount)
        {
            DrawCommandResponse localSnapshot = BuildLocalCompletionSnapshot(pendingSnapshot, executedCount);
            if (_llmClient == null || string.IsNullOrWhiteSpace(taskId))
            {
                return localSnapshot;
            }

            try
            {
                PlannerTaskDetailResponse syncedDetail = await _llmClient.RecordPlannerLocalResultAsync(
                    taskId,
                    executedCount,
                    pendingSnapshot != null ? pendingSnapshot.TraceId : string.Empty,
                    "本地 AutoCAD 已应用预览命令",
                    true,
                    PlannerLocalResultDetailsBuilder.Build(taskId, GetPlannerPreviewCommands(pendingSnapshot), executedCount));
                DrawCommandResponse syncedSnapshot = CreatePlannerSnapshot(syncedDetail);
                await ApplyHarnessEventsAsync(taskId, syncedSnapshot);
                return syncedSnapshot ?? localSnapshot;
            }
            catch (Exception ex)
            {
                Logger.Warn("Planner local result sync failed: " + ex.Message);
                return localSnapshot;
            }
        }

        private async Task ResumeParameterRequestAsync(string taskId, string resumeMessage)
        {
            if (string.IsNullOrWhiteSpace(taskId) || _llmClient == null)
            {
                AddMessage("system", "当前任务不可继续。请重新打开任务中心后再试。");
                return;
            }

            SetStatus("继续任务中");
            DrawCommandResponse response = await _llmClient.ResumePlannerTaskAsync(taskId, resumeMessage);
            if (response == null)
            {
                AddMessage("system", "当前任务暂时无法继续。");
                return;
            }

            DrawCommandResponse snapshot = await TryRefreshPlannerTaskSnapshotAsync(response);
            DisplayPlannerTaskSnapshot(snapshot, false);
            AddMessage("assistant", BuildPlannerReplyFallback(snapshot));
            AddPlannerProcessPanel(snapshot);

            if (IsPlannerWaitingUser(snapshot))
            {
                AddPlannerActionPanel(snapshot);
                AddMessage("system", BuildPlannerFollowUpHint(snapshot));
                SetStatus(IsPlannerAwaitingWriteConfirmation(snapshot) ? "等待应用到图纸" : "任务等待补充信息");
            }
            else if (IsPlannerFailed(snapshot))
            {
                AddMessage("system", BuildPlannerFailureHint(snapshot));
                SetStatus("任务继续失败");
            }
            else if (IsPlannerCompleted(snapshot))
            {
                AddMessage("system", BuildPlannerCompletionHint(snapshot));
                SetStatus("任务已完成");
            }
            else
            {
                AddMessage("system", BuildPlannerExecutionEventSummary(GetPlannerExecutionEvents(snapshot)));
                SetStatus("任务已继续");
            }

            _taskPanelSelectedTaskId = !string.IsNullOrWhiteSpace(snapshot.PlannerSessionId) ? snapshot.PlannerSessionId : taskId;
            await RefreshTaskCenterIfOpenAsync(_taskPanelSelectedTaskId);
            FocusInputBox(true);
        }

        private async Task DenyPlannerTaskPermissionAsync(string taskId)
        {
            SetStatus("正在拒绝写图权限");
            PlannerTaskDetailResponse detail = await _llmClient.RecordPlannerPermissionDecisionAsync(
                taskId,
                "deny",
                "用户拒绝将当前预览写入图纸。",
                string.Empty);
            if (detail == null)
            {
                AddMessage("system", "当前任务暂时无法拒绝写图权限。");
                return;
            }

            if (string.Equals(_llmClient.GetCurrentPlannerSessionId(), detail.TaskId, StringComparison.OrdinalIgnoreCase))
            {
                _llmClient.SetCurrentPlannerSessionId(string.Empty);
            }

            ClearPendingWriteConfirmation();
            ClearReviewPanel();
            _lastReviewSnapshot = null;
            _taskPanelSelectedTaskId = detail.TaskId ?? string.Empty;

            DrawCommandResponse snapshot = CreatePlannerSnapshot(detail);
            DisplayPlannerTaskSnapshot(snapshot, true);
            AddPlannerProcessPanel(snapshot);
            AddMessage("system", "已拒绝写入当前预览。你可以调整要求后重新发起任务。");
            SetStatus("已拒绝写图权限");
            await RefreshTaskCenterIfOpenAsync(_taskPanelSelectedTaskId);
            FocusInputBox(true);
        }

        private async Task CancelPlannerTaskAsync(string taskId)
        {
            SetStatus("取消任务中");
            PlannerTaskDetailResponse detail = await _llmClient.CancelPlannerTaskAsync(taskId);
            if (detail == null)
            {
                AddMessage("system", "当前任务不可取消。");
                return;
            }

            if (string.Equals(_llmClient.GetCurrentPlannerSessionId(), detail.TaskId, StringComparison.OrdinalIgnoreCase))
            {
                _llmClient.SetCurrentPlannerSessionId(string.Empty);
            }
            _taskPanelSelectedTaskId = string.Empty;

            DrawCommandResponse snapshot = CreatePlannerSnapshot(detail);
            DisplayPlannerTaskSnapshot(snapshot, true);
            AddMessage("system", "任务已取消。你可以打开其他任务，或开始新的智能体会话。");
            SetStatus("任务已取消");
            await RefreshTaskCenterIfOpenAsync();
        }

        private async Task RefreshTaskCenterIfOpenAsync(string selectedTaskId = null)
        {
            if (TaskCenterDrawer != null && TaskCenterDrawer.Visibility == Visibility.Visible)
            {
                await ShowRecentTasksPanelAsync(null, selectedTaskId);
            }
        }

        private void DisplayPlannerTaskSnapshot(DrawCommandResponse snapshot, bool keepTerminalStatusVisible)
        {
            StepTrackerHandle tracker = SyncPlannerTaskStepper(null, snapshot);
            if (tracker == null)
            {
                return;
            }

            if (IsPlannerAwaitingWriteConfirmation(snapshot))
            {
                SetPendingWriteConfirmation(snapshot);
            }
            else
            {
                ClearPendingWriteConfirmation();
            }

            if (IsPlannerWaitingUser(snapshot))
            {
                int progressCount = ResolvePlannerProgressCount(tracker, snapshot);
                UpdateTaskStepper(tracker, progressCount);
                if (IsPlannerAwaitingWriteConfirmation(snapshot))
                {
                    tracker.TitleText.Text = "等待应用到图纸(" + progressCount + "/" + tracker.ItemTexts.Count + ")";
                    return;
                }
                tracker.TitleText.Text = "待补充信息(" + progressCount + "/" + tracker.ItemTexts.Count + ")";
                return;
            }

            if (IsPlannerCompleted(snapshot))
            {
                UpdateTaskStepper(tracker, tracker.ItemTexts.Count);
                tracker.TitleText.Text = "已完成(" + tracker.ItemTexts.Count + "/" + tracker.ItemTexts.Count + ")";
                if (!keepTerminalStatusVisible)
                {
                    ClearTaskStepper();
                }
                return;
            }

            if (IsPlannerFailed(snapshot))
            {
                int progressCount = Math.Max(1, ResolvePlannerProgressCount(tracker, snapshot));
                UpdateTaskStepper(tracker, progressCount);
                tracker.TitleText.Text = "失败任务(" + progressCount + "/" + tracker.ItemTexts.Count + ")";
                if (!keepTerminalStatusVisible)
                {
                    ClearTaskStepper();
                }
                return;
            }

            int activeProgress = ResolvePlannerProgressCount(tracker, snapshot);
            UpdateTaskStepper(tracker, activeProgress);
            tracker.TitleText.Text = "任务详情(" + activeProgress + "/" + tracker.ItemTexts.Count + ")";
        }

        private static DrawCommandResponse CreatePlannerSnapshot(PlannerTaskDetailResponse detail)
        {
            if (detail == null)
            {
                return null;
            }

            return new DrawCommandResponse
            {
                ReplyText = detail.FinalResponse,
                PlannerSessionId = detail.TaskId,
                TraceId = detail.TraceId,
                PlannerState = detail.PlannerState,
                TaskStatus = detail.TaskStatus,
                ExecutedTools = detail.PlannerState != null ? detail.PlannerState.ExecutedTools : null,
                SelectedSkills = detail.PlannerState != null ? detail.PlannerState.SelectedSkills : null,
                ExecutionEvents = detail.PlannerState != null ? detail.PlannerState.ExecutionEvents : null,
                HarnessEvents = new List<HarnessEventResponse>(),
                PlannerCompletedSteps = detail.PlannerState != null ? detail.PlannerState.CompletedSteps : null,
                PlannerPendingSteps = detail.PlannerState != null ? detail.PlannerState.PendingSteps : null,
                AskUserType = detail.PlannerState != null ? detail.PlannerState.AskUserType : null,
                AskUserHint = detail.PlannerState != null ? detail.PlannerState.AskUserHint : null,
                ActiveStep = detail.ActiveStep,
                CreatedAt = detail.CreatedAt,
                UpdatedAt = detail.UpdatedAt,
                Resumable = detail.Resumable,
                Retryable = detail.Retryable,
                Cancellable = detail.Cancellable,
                LastError = detail.LastError
            };
        }

        private static string BuildTaskOpenHint(PlannerTaskDetailResponse detail, bool armSession)
        {
            if (detail == null)
            {
                return "任务详情已加载。";
            }

            if (armSession && detail.Resumable)
            {
                if (IsPlannerAwaitingWriteConfirmation(detail))
                {
                    return "已切换到任务「" + detail.UserGoal + "」。当前任务已有更改预览，点击“应用到图纸”或回复“确认执行”即可继续。";
                }

                string hint = detail.PlannerState != null ? detail.PlannerState.AskUserHint : string.Empty;
                if (!string.IsNullOrWhiteSpace(hint))
                {
                    return "已切换到任务「" + detail.UserGoal + "」。\n" + hint + "\n继续输入后将自动续跑当前任务。";
                }

                return "已切换到任务「" + detail.UserGoal + "」。继续输入后将自动续跑当前任务。";
            }

            if (string.Equals(detail.TaskStatus, "failed", StringComparison.OrdinalIgnoreCase))
            {
                return "已打开失败任务。你可以直接点击重试，或先查看失败步骤和原因。";
            }

            if (string.Equals(detail.TaskStatus, "completed", StringComparison.OrdinalIgnoreCase))
            {
                return "已打开已完成任务，可查看步骤和执行摘要。";
            }

            return "已打开任务详情。";
        }

        private static string BuildRecentTaskMeta(PlannerTaskSummaryResponse task)
        {
            if (task == null)
            {
                return string.Empty;
            }

            List<string> fragments = new List<string>();
            string status = BuildTaskStatusLabel(task.TaskStatus);
            if (!string.IsNullOrWhiteSpace(status))
            {
                fragments.Add(status);
            }

            if (!string.IsNullOrWhiteSpace(task.ActiveStep))
            {
                fragments.Add("当前步骤: " + task.ActiveStep.Trim());
            }

            if (task.LastError != null && !string.IsNullOrWhiteSpace(task.LastError.Message))
            {
                fragments.Add("Failure: " + task.LastError.Message.Trim());
            }

            string updated = FormatTaskTimestamp(task.UpdatedAt);
            if (!string.IsNullOrWhiteSpace(updated))
            {
                fragments.Add("更新于 " + updated);
            }

            return string.Join(" · ", fragments);
        }

        private static string BuildTaskDetailMeta(PlannerTaskDetailResponse detail)
        {
            if (detail == null)
            {
                return string.Empty;
            }

            List<string> fragments = new List<string>();
            string status = BuildTaskStatusLabel(detail.TaskStatus);
            if (!string.IsNullOrWhiteSpace(status))
            {
                fragments.Add(status);
            }

            if (!string.IsNullOrWhiteSpace(detail.ActiveStep))
            {
                fragments.Add("当前步骤: " + detail.ActiveStep.Trim());
            }

            string updated = FormatTaskTimestamp(detail.UpdatedAt);
            if (!string.IsNullOrWhiteSpace(updated))
            {
                fragments.Add("更新于 " + updated);
            }

            if (!string.IsNullOrWhiteSpace(detail.TraceId))
            {
                fragments.Add("trace " + ShortTraceId(detail.TraceId));
            }

            return string.Join(" · ", fragments);
        }

        private static string ShortTraceId(string traceId)
        {
            string normalized = (traceId ?? string.Empty).Trim();
            if (normalized.Length <= 8)
            {
                return normalized;
            }

            return normalized.Substring(0, 8);
        }

        private static string BuildSelectedTaskSummary(PlannerTaskDetailResponse detail)
        {
            if (detail == null)
            {
                return string.Empty;
            }

            if (IsPlannerAwaitingWriteConfirmation(detail))
            {
                return "当前任务已有更改预览，尚未应用到图纸。";
            }

            if (detail.LastError != null && !string.IsNullOrWhiteSpace(detail.LastError.Message))
            {
                return "失败原因: " + detail.LastError.Message.Trim();
            }

            if (!string.IsNullOrWhiteSpace(detail.FinalResponse))
            {
                return detail.FinalResponse.Trim();
            }

            if (detail.PlannerState != null && detail.PlannerState.ExecutionEvents != null && detail.PlannerState.ExecutionEvents.Count > 0)
            {
                return BuildPlannerExecutionEventSummary(detail.PlannerState.ExecutionEvents);
            }

            return string.Empty;
        }

        private static string NormalizeTaskPanelFilter(string filter)
        {
            string normalized = (filter ?? "all").Trim().ToLowerInvariant();
            return normalized.Length == 0 ? "all" : normalized;
        }

        private static string BuildTaskStatusLabel(string taskStatus)
        {
            switch ((taskStatus ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "created":
                    return "已创建";
                case "running":
                    return "进行中";
                case "waiting_user":
                    return "等待补充";
                case "completed":
                    return "已完成";
                case "failed":
                    return "失败";
                case "cancelled":
                    return "已取消";
                default:
                    return string.Empty;
            }
        }

        private static string FormatTaskTimestamp(string timestamp)
        {
            if (string.IsNullOrWhiteSpace(timestamp))
            {
                return string.Empty;
            }

            DateTime parsed;
            if (!DateTime.TryParse(timestamp, out parsed))
            {
                return timestamp.Trim();
            }

            return parsed.ToLocalTime().ToString("MM-dd HH:mm");
        }

        private static string GetPlannerTaskStatus(DrawCommandResponse response)
        {
            if (response == null)
            {
                return string.Empty;
            }

            if (response.PlannerState != null && !string.IsNullOrWhiteSpace(response.PlannerState.TaskStatus))
            {
                return response.PlannerState.TaskStatus;
            }

            return response.TaskStatus ?? string.Empty;
        }

        private static List<string> GetPlannerExecutedTools(DrawCommandResponse response)
        {
            if (response != null && response.PlannerState != null && response.PlannerState.ExecutedTools != null)
            {
                return response.PlannerState.ExecutedTools;
            }

            return response != null && response.ExecutedTools != null
                ? response.ExecutedTools
                : new List<string>();
        }

        private static List<PlannerExecutionEventResponse> GetPlannerExecutionEvents(DrawCommandResponse response)
        {
            if (response != null && response.PlannerState != null && response.PlannerState.ExecutionEvents != null)
            {
                return response.PlannerState.ExecutionEvents;
            }

            return response != null && response.ExecutionEvents != null
                ? response.ExecutionEvents
                : new List<PlannerExecutionEventResponse>();
        }

        private static List<string> GetPlannerCompletedSteps(DrawCommandResponse response)
        {
            if (response != null && response.PlannerState != null && response.PlannerState.CompletedSteps != null)
            {
                return response.PlannerState.CompletedSteps;
            }

            return response != null && response.PlannerCompletedSteps != null
                ? response.PlannerCompletedSteps
                : new List<string>();
        }

        private static List<string> GetPlannerPendingSteps(DrawCommandResponse response)
        {
            if (response != null && response.PlannerState != null && response.PlannerState.PendingSteps != null)
            {
                return response.PlannerState.PendingSteps;
            }

            return response != null && response.PlannerPendingSteps != null
                ? response.PlannerPendingSteps
                : new List<string>();
        }

        private static string GetPlannerAskUserType(DrawCommandResponse response)
        {
            if (response != null && response.PlannerState != null && !string.IsNullOrWhiteSpace(response.PlannerState.AskUserType))
            {
                return response.PlannerState.AskUserType;
            }

            return response != null ? (response.AskUserType ?? string.Empty) : string.Empty;
        }

        private static string GetPlannerAskUserHint(DrawCommandResponse response)
        {
            if (response != null && response.PlannerState != null && !string.IsNullOrWhiteSpace(response.PlannerState.AskUserHint))
            {
                return response.PlannerState.AskUserHint;
            }

            return response != null ? (response.AskUserHint ?? string.Empty) : string.Empty;
        }

        private static string GetPlannerAgentApproval(DrawCommandResponse response)
        {
            return response != null && response.PlannerState != null
                ? response.PlannerState.AgentApproval ?? string.Empty
                : string.Empty;
        }

        private static string GetPlannerPendingPermissionAction(DrawCommandResponse response)
        {
            return response != null && response.PlannerState != null
                ? response.PlannerState.PendingPermissionAction ?? string.Empty
                : string.Empty;
        }

        private static string GetPlannerPermissionSummary(DrawCommandResponse response)
        {
            return response != null && response.PlannerState != null
                ? response.PlannerState.PermissionSummary ?? string.Empty
                : string.Empty;
        }

        private static bool IsPlannerWaitingUser(DrawCommandResponse response)
        {
            return string.Equals(GetPlannerTaskStatus(response), "waiting_user", StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsPlannerAwaitingWriteConfirmation(DrawCommandResponse response)
        {
            return string.Equals(GetPlannerAskUserType(response).Trim(), "confirm_write", StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsPlannerAwaitingSkillParameters(DrawCommandResponse response)
        {
            return IsPlannerWaitingUser(response)
                && !IsPlannerAwaitingWriteConfirmation(response)
                && string.Equals(GetPlannerAskUserType(response).Trim(), "skill_parameters", StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsPlannerAwaitingWriteConfirmation(PlannerTaskDetailResponse detail)
        {
            string askUserType = detail != null && detail.PlannerState != null
                ? detail.PlannerState.AskUserType
                : string.Empty;
            return string.Equals((askUserType ?? string.Empty).Trim(), "confirm_write", StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsPlannerFailed(DrawCommandResponse response)
        {
            return string.Equals(GetPlannerTaskStatus(response), "failed", StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsPlannerCompleted(DrawCommandResponse response)
        {
            return string.Equals(GetPlannerTaskStatus(response), "completed", StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsLegacyServiceCommandFallback(DrawCommandResponse response)
        {
            return response != null
                && response.Commands != null
                && response.Commands.Count > 0
                && response.LegacyFallbackUsed;
        }

        private static bool HasIncompatibleLegacyCommands(DrawCommandResponse response)
        {
            string plannerTaskStatus = GetPlannerTaskStatus(response);
            return response != null
                && response.Commands != null
                && response.Commands.Count > 0
                && !response.LegacyFallbackUsed
                && string.IsNullOrWhiteSpace(plannerTaskStatus);
        }

        private void ReportLegacyFallbackNotice()
        {
            AddMessage("system", "当前智能体响应显式返回了 legacy commands，已按兼容路径执行。后续主路径将继续以 Planner 状态对象为准。");
        }

        private static string BuildIncompatibleLegacyCommandMessage(DrawCommandResponse response)
        {
            if (response != null && !string.IsNullOrWhiteSpace(response.ReplyText))
            {
                return response.ReplyText + "\n\n但当前响应未满足执行条件：commands 兼容路径现在要求显式返回 legacy_fallback_used=true。";
            }

            return "当前智能体响应包含 legacy commands，但没有显式 legacy_fallback_used 标记，因此未执行兼容路径。";
        }

        private StepTrackerHandle SyncPlannerTaskStepper(StepTrackerHandle tracker, DrawCommandResponse response)
        {
            List<string> plannerSteps = BuildPlannerSteps(response);
            if (plannerSteps.Count == 0)
            {
                return tracker;
            }

            if (tracker == null || tracker.ItemTexts == null || tracker.ItemTexts.Count != plannerSteps.Count)
            {
                return AddTaskStepper(plannerSteps);
            }

            for (int i = 0; i < plannerSteps.Count; i++)
            {
                tracker.ItemTexts[i].Text = plannerSteps[i];
            }

            return tracker;
        }

        private static List<string> BuildPlannerSteps(DrawCommandResponse response)
        {
            List<string> steps = new List<string>();
            List<string> completedSteps = GetPlannerCompletedSteps(response);
            List<string> pendingSteps = GetPlannerPendingSteps(response);

            for (int i = 0; i < completedSteps.Count; i++)
            {
                string step = (completedSteps[i] ?? string.Empty).Trim();
                if (step.Length > 0)
                {
                    steps.Add(step);
                }
            }

            for (int i = 0; i < pendingSteps.Count; i++)
            {
                string step = (pendingSteps[i] ?? string.Empty).Trim();
                if (step.Length > 0)
                {
                    steps.Add(step);
                }
            }

            if (steps.Count == 0 && response != null && !string.IsNullOrWhiteSpace(response.ActiveStep))
            {
                steps.Add(response.ActiveStep.Trim());
            }

            return steps;
        }

        private static int ResolvePlannerProgressCount(StepTrackerHandle tracker, DrawCommandResponse response)
        {
            List<string> completedSteps = GetPlannerCompletedSteps(response);
            if (completedSteps.Count > 0)
            {
                return completedSteps.Count;
            }

            if (tracker == null || tracker.ItemTexts == null)
            {
                return 0;
            }

            int executedToolCount = GetPlannerExecutedTools(response).Count;
            return Math.Min(Math.Max(1, executedToolCount + 1), tracker.ItemTexts.Count);
        }

        private static string BuildPlannerFollowUpHint(DrawCommandResponse response)
        {
            string askUserType = GetPlannerAskUserType(response).Trim();
            string hint = GetPlannerAskUserHint(response).Trim();

            if (IsPlannerAwaitingWriteConfirmation(response))
            {
                return "确认后会把这些更改应用到当前图纸。你可以点击“应用到图纸”，或回复“确认执行”。";
            }

            string prefix;
            switch (askUserType.ToLowerInvariant())
            {
                case "missing_dimension":
                case "dimension":
                    prefix = "智能体正在等待你补充尺寸信息。";
                    break;
                case "missing_target":
                case "target_object":
                    prefix = "智能体正在等待你确认目标对象。";
                    break;
                case "missing_constraint":
                case "constraint":
                    prefix = "智能体正在等待你补充约束条件。";
                    break;
                case "missing_context":
                    prefix = "智能体正在等待你补充当前任务所需的上下文信息。";
                    break;
                case "confirmation":
                    prefix = "智能体正在等待你确认当前方案。";
                    break;
                default:
                    prefix = "智能体正在等待你补充信息。";
                    break;
            }

            if (string.IsNullOrWhiteSpace(hint))
            {
                return prefix + " 可直接继续输入下一条消息，当前 Planner 会话会自动续跑。";
            }

            return prefix + "\n" + hint + "\n当前 Planner 会话会自动续跑。";
        }

        private static string BuildPlannerReplyFallback(DrawCommandResponse response)
        {
            if (response != null && !string.IsNullOrWhiteSpace(response.ReplyText))
            {
                if (IsPlannerAwaitingWriteConfirmation(response))
                {
                    string normalizedReply = NormalizePlannerPreviewSummary(response.ReplyText);
                    if (IsPlannerTechnicalDryRunText(response.ReplyText) || string.IsNullOrWhiteSpace(normalizedReply))
                    {
                        return "我已经准备好更改预览，确认后会应用到当前图纸。";
                    }

                    return normalizedReply;
                }

                return response.ReplyText;
            }

            if (IsPlannerWaitingUser(response))
            {
                if (IsPlannerAwaitingWriteConfirmation(response))
                {
                    return "我已经准备好更改预览，确认后会应用到当前图纸。";
                }
                return "我还需要你补充一点信息，才能继续当前任务。";
            }

            if (GetPlannerExecutedTools(response).Count > 0)
            {
                return "我已执行当前规划步骤，并会继续基于最新结果推进任务。";
            }

            if (string.Equals(GetPlannerTaskStatus(response), "completed", StringComparison.OrdinalIgnoreCase))
            {
                return "任务已完成。";
            }

            if (string.Equals(GetPlannerTaskStatus(response), "failed", StringComparison.OrdinalIgnoreCase))
            {
                if (response != null && response.LastError != null && !string.IsNullOrWhiteSpace(response.LastError.Message))
                {
                    return response.LastError.Message;
                }

                return "任务未能完成。请补充更明确的信息后重试。";
            }

            return "智能体已处理当前请求。";
        }

        private static string BuildPlannerExecutionEventSummary(List<PlannerExecutionEventResponse> executionEvents)
        {
            List<string> fragments = new List<string>();
            for (int i = 0; i < executionEvents.Count; i++)
            {
                PlannerExecutionEventResponse executionEvent = executionEvents[i];
                if (executionEvent == null || string.IsNullOrWhiteSpace(executionEvent.ToolName))
                {
                    continue;
                }

                string statusLabel = string.Equals(executionEvent.Status, "failed", StringComparison.OrdinalIgnoreCase)
                    ? "失败"
                    : "完成";
                string normalizedSummary = GetPlannerEventDisplaySummary(executionEvent);
                string summary = string.IsNullOrWhiteSpace(normalizedSummary)
                    ? string.Empty
                    : "(" + normalizedSummary + ")";
                string requestIdSuffix = string.Equals(executionEvent.Status, "failed", StringComparison.OrdinalIgnoreCase)
                    && !string.IsNullOrWhiteSpace(executionEvent.RequestId)
                    ? "[req:" + executionEvent.RequestId.Trim() + "]"
                    : string.Empty;
                fragments.Add(executionEvent.ToolName + statusLabel + summary + requestIdSuffix);
            }

            if (fragments.Count == 0)
            {
                return "智能体已执行 Planner 工具步骤。";
            }

            return "智能体工具执行摘要: " + string.Join("；", fragments) + "。";
        }

        private static bool HasPlannerPreview(DrawCommandResponse response)
        {
            return IsPlannerAwaitingWriteConfirmation(response)
                && (!string.IsNullOrWhiteSpace(GetPlannerAskUserHint(response)) || GetPlannerPreviewEvents(response).Count > 0 || GetPlannerExecutedTools(response).Count > 0);
        }

        private static bool HasPlannerProcessPayload(DrawCommandResponse response)
        {
            if (response == null)
            {
                return false;
            }

            return !string.IsNullOrWhiteSpace(GetPlannerTaskStatus(response))
                || GetPlannerCompletedSteps(response).Count > 0
                || GetPlannerPendingSteps(response).Count > 0
                || GetPlannerHarnessEvents(response).Count > 0
                || GetPlannerExecutionEvents(response).Count > 0
                || GetPlannerExecutedTools(response).Count > 0
                || !string.IsNullOrWhiteSpace(GetPlannerAskUserType(response));
        }

        private static List<HarnessEventResponse> GetPlannerHarnessEvents(DrawCommandResponse response)
        {
            if (response != null && response.HarnessEvents != null)
            {
                return response.HarnessEvents;
            }

            return new List<HarnessEventResponse>();
        }

        private static List<PlannerExecutionEventResponse> GetPlannerPreviewEvents(DrawCommandResponse response)
        {
            return IsPlannerAwaitingWriteConfirmation(response)
                ? GetPlannerExecutionEvents(response)
                : new List<PlannerExecutionEventResponse>();
        }

        private static string BuildPlannerPreviewToolNames(DrawCommandResponse response, List<PlannerExecutionEventResponse> previewEvents)
        {
            List<string> toolNames = new List<string>();
            for (int i = 0; i < previewEvents.Count; i++)
            {
                string toolName = previewEvents[i] != null ? (previewEvents[i].ToolName ?? string.Empty).Trim() : string.Empty;
                if (toolName.Length == 0 || toolNames.Contains(toolName))
                {
                    continue;
                }

                toolNames.Add(toolName);
            }

            if (toolNames.Count == 0)
            {
                List<string> executedTools = GetPlannerExecutedTools(response);
                for (int i = 0; i < executedTools.Count; i++)
                {
                    string toolName = (executedTools[i] ?? string.Empty).Trim();
                    if (toolName.Length == 0 || toolNames.Contains(toolName))
                    {
                        continue;
                    }

                    toolNames.Add(toolName);
                }
            }

            return string.Join("、", toolNames);
        }

        private static string BuildPlannerPreviewNextStep(DrawCommandResponse response)
        {
            string hint = GetPlannerAskUserHint(response).Trim();
            if (!string.IsNullOrWhiteSpace(hint))
            {
                if (!IsPlannerTechnicalDryRunText(hint))
                {
                    return NormalizePlannerPreviewSummary(hint) + " 确认后会把这些更改应用到当前图纸。";
                }
            }

            return "确认后会把这些更改应用到当前图纸；如需调整，可以继续补充要求。";
        }

        private static string BuildPlannerCompletionHint(DrawCommandResponse response)
        {
            List<PlannerExecutionEventResponse> executionEvents = GetPlannerExecutionEvents(response);
            if (executionEvents.Count > 0)
            {
                return "智能体任务已完成。" + BuildPlannerExecutionEventSummary(executionEvents);
            }

            List<string> completedSteps = GetPlannerCompletedSteps(response);
            if (completedSteps.Count > 0)
            {
                return "智能体任务已完成。完成步骤: " + string.Join(" -> ", completedSteps) + "。";
            }

            List<string> executedTools = GetPlannerExecutedTools(response);
            if (executedTools.Count > 0)
            {
                return "智能体任务已完成，执行工具: " + string.Join("、", executedTools) + "。";
            }

            return "智能体任务已完成。";
        }

        private static string BuildPlannerFailureHint(DrawCommandResponse response)
        {
            if (response != null && response.LastError != null && !string.IsNullOrWhiteSpace(response.LastError.Message))
            {
                string technicalDetail = response.LastError.TechnicalDetail;
                if (!string.IsNullOrWhiteSpace(technicalDetail))
                {
                    return "智能体任务未完成。原因: " + response.LastError.Message.Trim() + "。详细信息: " + technicalDetail.Trim();
                }

                return "智能体任务未完成。原因: " + response.LastError.Message.Trim() + "。";
            }

            string hint = GetPlannerAskUserHint(response).Trim();
            if (!string.IsNullOrWhiteSpace(hint))
            {
                return "智能体任务未完成。建议先补充以下信息后重试: " + hint;
            }

            List<PlannerExecutionEventResponse> executionEvents = GetPlannerExecutionEvents(response);
            if (executionEvents.Count > 0)
            {
                return "智能体任务未完成。" + BuildPlannerExecutionEventSummary(executionEvents) + " 你可以补充更明确的约束后重试。";
            }

            List<string> executedTools = GetPlannerExecutedTools(response);
            if (executedTools.Count > 0)
            {
                return "智能体任务未完成。已执行工具: " + string.Join("、", executedTools) + "。你可以补充更明确的约束后重试。";
            }

            return "智能体任务未完成。你可以补充更明确的约束，或直接重试。";
        }

        private async Task<DrawCommandResponse> TryRefreshPlannerTaskSnapshotAsync(DrawCommandResponse response)
        {
            if (_llmClient == null || response == null)
            {
                return response;
            }

            string taskId = !string.IsNullOrWhiteSpace(response.PlannerSessionId)
                ? response.PlannerSessionId
                : _llmClient.GetCurrentPlannerSessionId();
            if (string.IsNullOrWhiteSpace(taskId))
            {
                return response;
            }

            try
            {
                PlannerTaskDetailResponse detail = await _llmClient.GetPlannerTaskDetailAsync(taskId);
                DrawCommandResponse snapshot = MergePlannerTaskDetail(response, detail);
                await ApplyHarnessEventsAsync(taskId, snapshot);
                return snapshot;
            }
            catch (Exception ex)
            {
                Logger.Warn("Planner task detail refresh failed: " + ex.Message);
                return response;
            }
        }

        private async Task<DrawCommandResponse> TryRefreshPlannerTaskSnapshotByIdAsync(string taskId, DrawCommandResponse fallback)
        {
            if (_llmClient == null || string.IsNullOrWhiteSpace(taskId))
            {
                return fallback;
            }

            try
            {
                PlannerTaskDetailResponse detail = await _llmClient.GetPlannerTaskDetailAsync(taskId);
                if (detail == null)
                {
                    return fallback;
                }
                DrawCommandResponse snapshot = MergePlannerTaskDetail(fallback ?? CreatePlannerSnapshot(detail), detail);
                await ApplyHarnessEventsAsync(taskId, snapshot);
                return snapshot;
            }
            catch (Exception ex)
            {
                Logger.Warn("Planner task detail refresh by id failed: " + ex.Message);
                return fallback;
            }
        }

        private async Task ApplyHarnessEventsAsync(string taskId, DrawCommandResponse snapshot)
        {
            if (_llmClient == null || snapshot == null || string.IsNullOrWhiteSpace(taskId))
            {
                return;
            }

            try
            {
                PlannerTaskEventsResponse eventsResponse = await _llmClient.GetPlannerTaskEventsAsync(taskId);
                if (eventsResponse != null && eventsResponse.Events != null)
                {
                    snapshot.HarnessEvents = eventsResponse.Events;
                }
            }
            catch (Exception ex)
            {
                Logger.Warn("Planner harness events refresh failed: " + ex.Message);
            }
        }

        private static DrawCommandResponse MergePlannerTaskDetail(DrawCommandResponse response, PlannerTaskDetailResponse detail)
        {
            if (response == null || detail == null)
            {
                return response;
            }

            return new DrawCommandResponse
            {
                Commands = response.Commands,
                Explanation = response.Explanation,
                ReplyText = !string.IsNullOrWhiteSpace(response.ReplyText) ? response.ReplyText : detail.FinalResponse,
                LegacyFallbackUsed = response.LegacyFallbackUsed,
                PlannerSessionId = !string.IsNullOrWhiteSpace(response.PlannerSessionId) ? response.PlannerSessionId : detail.TaskId,
                TraceId = !string.IsNullOrWhiteSpace(response.TraceId) ? response.TraceId : detail.TraceId,
                PlannerState = detail.PlannerState ?? response.PlannerState,
                TaskStatus = !string.IsNullOrWhiteSpace(detail.TaskStatus) ? detail.TaskStatus : response.TaskStatus,
                ExecutedTools = detail.PlannerState != null && detail.PlannerState.ExecutedTools != null ? detail.PlannerState.ExecutedTools : response.ExecutedTools,
                SelectedSkills = detail.PlannerState != null && detail.PlannerState.SelectedSkills != null ? detail.PlannerState.SelectedSkills : response.SelectedSkills,
                ExecutionEvents = detail.PlannerState != null && detail.PlannerState.ExecutionEvents != null ? detail.PlannerState.ExecutionEvents : response.ExecutionEvents,
                HarnessEvents = response.HarnessEvents,
                PlannerCompletedSteps = detail.PlannerState != null && detail.PlannerState.CompletedSteps != null ? detail.PlannerState.CompletedSteps : response.PlannerCompletedSteps,
                PlannerPendingSteps = detail.PlannerState != null && detail.PlannerState.PendingSteps != null ? detail.PlannerState.PendingSteps : response.PlannerPendingSteps,
                AskUserType = detail.PlannerState != null && !string.IsNullOrWhiteSpace(detail.PlannerState.AskUserType) ? detail.PlannerState.AskUserType : response.AskUserType,
                AskUserHint = detail.PlannerState != null && !string.IsNullOrWhiteSpace(detail.PlannerState.AskUserHint) ? detail.PlannerState.AskUserHint : response.AskUserHint,
                ActiveStep = detail.ActiveStep,
                CreatedAt = detail.CreatedAt,
                UpdatedAt = detail.UpdatedAt,
                Resumable = detail.Resumable,
                Retryable = detail.Retryable,
                Cancellable = detail.Cancellable,
                LastError = detail.LastError
            };
        }

        private void TaskStepperContainer_MouseLeftButtonUp(object sender, MouseButtonEventArgs e)
        {
            Border container = sender as Border;
            StepTrackerHandle tracker = container != null ? container.Tag as StepTrackerHandle : null;
            if (tracker == null)
            {
                return;
            }

            SetTaskStepperCollapsed(tracker, !tracker.IsCollapsed);
            e.Handled = true;
        }

        private void SetTaskStepperCollapsed(StepTrackerHandle tracker, bool isCollapsed)
        {
            tracker.IsCollapsed = isCollapsed;
            tracker.BodyPanel.Visibility = isCollapsed ? Visibility.Collapsed : Visibility.Visible;
            tracker.CollapseGlyphText.Text = isCollapsed ? "▸" : "▾";
            tracker.ToggleGlyphText.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString(isCollapsed ? "#D9DEE3" : "#8B949E"));
            MessageScroller.ScrollToEnd();
        }

        private static List<string> ParseTaskPlan(string response)
        {
            List<string> steps = new List<string>();
            if (string.IsNullOrWhiteSpace(response))
            {
                return steps;
            }

            string[] lines = response.Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries);
            for (int i = 0; i < lines.Length; i++)
            {
                string cleaned = Regex.Replace(lines[i], "^[\\-\\*\\d\\.\\s、]+", string.Empty).Trim();
                if (cleaned.Length == 0)
                {
                    continue;
                }

                steps.Add(cleaned);
                if (steps.Count == 5)
                {
                    break;
                }
            }

            return steps;
        }

        private static List<string> BuildFallbackPlan(string attachmentName, string attachmentText)
        {
            List<string> steps = new List<string>();
            steps.Add("梳理当前用户需求");
            if (!string.IsNullOrWhiteSpace(attachmentName) || !string.IsNullOrWhiteSpace(attachmentText))
            {
                steps.Add("读取并提取附件信息");
            }

            steps.Add("组织模型请求上下文");
            steps.Add("生成并校验回复结果");
            steps.Add("反馈执行结果与状态");
            return steps;
        }

        private void SetPendingImage(BitmapSource image, string fileName)
        {
            PngBitmapEncoder encoder = new PngBitmapEncoder();
            encoder.Frames.Add(BitmapFrame.Create(image));
            using (MemoryStream stream = new MemoryStream())
            {
                encoder.Save(stream);
                _pendingImage = stream.ToArray();
            }

            _pendingAttachmentName = fileName;
            _pendingAttachmentKind = "图片";
            _pendingAttachmentText = null;
            _pendingAttachmentMeta = "图片附件将随本次消息一起发送。";
            ShowImagePreview(image);
        }

        private void ClearPendingAttachment()
        {
            _pendingImage = null;
            _pendingAttachmentName = null;
            _pendingAttachmentKind = null;
            _pendingAttachmentText = null;
            _pendingAttachmentMeta = null;
            ImagePreview.Source = null;
            AttachmentShelf.Visibility = Visibility.Collapsed;
            AttachmentGlyphText.Visibility = Visibility.Collapsed;
        }

        private static string ExtractAttachmentText(string filePath, string extension)
        {
            string normalizedExtension = (extension ?? string.Empty).Trim().ToLowerInvariant();
            switch (normalizedExtension)
            {
                case ".txt":
                case ".md":
                case ".markdown":
                case ".json":
                case ".csv":
                case ".log":
                case ".cs":
                case ".xaml":
                case ".xml":
                    return File.ReadAllText(filePath);
                case ".docx":
                    return ExtractDocxText(filePath);
                default:
                    throw new InvalidOperationException("当前仅支持 txt、markdown、json、csv、代码文件和 docx 文本提取。");
            }
        }

        private static string ExtractDocxText(string filePath)
        {
            using (ZipArchive archive = ZipFile.OpenRead(filePath))
            {
                ZipArchiveEntry entry = archive.GetEntry("word/document.xml");
                if (entry == null)
                {
                    throw new InvalidOperationException("未找到 Word 正文内容。");
                }

                using (Stream stream = entry.Open())
                using (StreamReader reader = new StreamReader(stream, Encoding.UTF8))
                {
                    string xml = reader.ReadToEnd();
                    xml = Regex.Replace(xml, @"</w:p>", Environment.NewLine, RegexOptions.IgnoreCase);
                    xml = Regex.Replace(xml, @"<[^>]+>", string.Empty);
                    xml = WebUtility.HtmlDecode(xml);
                    return Regex.Replace(xml, @"\n{3,}", Environment.NewLine + Environment.NewLine).Trim();
                }
            }
        }

        private static string TruncateAttachmentText(string text, int maxLength, out bool truncated)
        {
            string normalized = (text ?? string.Empty).Trim();
            if (normalized.Length <= maxLength)
            {
                truncated = false;
                return normalized;
            }

            truncated = true;
            return normalized.Substring(0, maxLength);
        }

        private static string BuildAttachmentGlyph(string extension)
        {
            string glyph = (extension ?? string.Empty).Trim().TrimStart('.').ToUpperInvariant();
            if (glyph.Length == 0)
            {
                return "FILE";
            }

            return glyph.Length <= 4 ? glyph : glyph.Substring(0, 4);
        }

        private void UpdateConnectionModeButtonVisual()
        {
            if (CodeModeButton == null)
            {
                return;
            }

            string mode = GetSelectedConnectionMode();
            bool useServiceMode = string.Equals(mode, ConnectionModeService, StringComparison.OrdinalIgnoreCase);
            CodeModeButton.Content = GetConnectionModeShortName(mode) + " ▾";
            CodeModeButton.Background = Brushes.Transparent;
            CodeModeButton.BorderBrush = Brushes.Transparent;
            CodeModeButton.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#C8CDD4"));
            CodeModeButton.ToolTip = "当前为" + GetConnectionModeDisplayName(mode) + "，点击选择模式";

            if (AgentApprovalRow != null)
            {
                AgentApprovalRow.Visibility = useServiceMode ? Visibility.Visible : Visibility.Collapsed;
            }

            if (AgentApprovalComposerButton != null)
            {
                string approvalMode = GetConfiguredAgentApprovalMode();
                AgentApprovalComposerButton.Visibility = useServiceMode ? Visibility.Visible : Visibility.Collapsed;
                AgentApprovalComposerButton.Content = GetAgentApprovalDisplayName(approvalMode) + " ▾";
                AgentApprovalComposerButton.ToolTip = BuildAgentApprovalToolTip(approvalMode);
                AgentApprovalComposerButton.Background = Brushes.Transparent;
                AgentApprovalComposerButton.BorderBrush = Brushes.Transparent;
                AgentApprovalComposerButton.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#C8CDD4"));
            }

        }

        private void UpdateFooterState()
        {
            if (FooterModeText == null || FooterConnectionText == null || ConnectionIndicator == null)
            {
                return;
            }

            FooterModeText.Content = GetConnectionModeShortName(GetSelectedConnectionMode()) + " · v" + PluginVersion;
            FooterModeText.Visibility = Visibility.Visible;

            if (FooterNotificationButton != null)
            {
                FooterNotificationButton.Visibility = Visibility.Collapsed;
            }

            FooterConnectionText.Text = BuildFooterConnectionText();
            FooterConnectionButton.Visibility = Visibility.Visible;

            string color = _isBusy
                ? "#D7BA7D"
                : BuildFooterConnectionColor();
            ConnectionIndicator.Fill = new SolidColorBrush((Color)ColorConverter.ConvertFromString(color));
        }

        private void FooterMode_Click(object sender, RoutedEventArgs e)
        {
            ToggleConfig_Click(sender, e);
        }

        private void FooterNotification_Click(object sender, RoutedEventArgs e)
        {
            MessageBox.Show("暂无新的通知。\n后续这里会显示任务完成和需要确认的操作。", "AgentBridge 通知", MessageBoxButton.OK, MessageBoxImage.Information);
        }

        private async void FooterConnection_Click(object sender, RoutedEventArgs e)
        {
            CloseWorkSurfaceDrawers(DiagnosticsDrawer);
            await ShowDiagnosticsPanelAsync();
        }

        private string BuildFooterConnectionText()
        {
            if (_isBusy)
            {
                return "处理中";
            }

            if (UseServiceMode() && string.IsNullOrWhiteSpace(Config.Get("CADCOPILOT_API_BASE_URL", string.Empty)))
            {
                return "未连接";
            }

            return "已配置";
        }

        private string BuildFooterConnectionColor()
        {
            if (_isBusy)
            {
                return "#D7BA7D";
            }

            if (UseServiceMode() && string.IsNullOrWhiteSpace(Config.Get("CADCOPILOT_API_BASE_URL", string.Empty)))
            {
                return "#F14C4C";
            }

            return "#4EC9B0";
        }

        private string GetConfiguredAgentApprovalMode()
        {
            return NormalizeAgentApprovalMode(Config.Get("CADCOPILOT_AGENT_APPROVAL", AgentApprovalAnnotate));
        }

        private string GetSelectedAgentApprovalMode()
        {
            return GetComboBoxTag(AgentApprovalBox, GetConfiguredAgentApprovalMode());
        }

        private static string NormalizeAgentApprovalMode(string mode)
        {
            if (string.Equals(mode, AgentApprovalExecute, StringComparison.OrdinalIgnoreCase))
            {
                return AgentApprovalExecute;
            }

            if (string.Equals(mode, AgentApprovalFull, StringComparison.OrdinalIgnoreCase))
            {
                return AgentApprovalFull;
            }

            return AgentApprovalAnnotate;
        }

        private static string GetAgentApprovalDisplayName(string mode)
        {
            string normalized = NormalizeAgentApprovalMode(mode);
            if (string.Equals(normalized, AgentApprovalExecute, StringComparison.OrdinalIgnoreCase))
            {
                return "替我执行";
            }

            if (string.Equals(normalized, AgentApprovalFull, StringComparison.OrdinalIgnoreCase))
            {
                return "完全批准";
            }

            return "请求批准";
        }

        private static string BuildAgentApprovalToolTip(string mode)
        {
            string normalized = NormalizeAgentApprovalMode(mode);
            if (string.Equals(normalized, AgentApprovalExecute, StringComparison.OrdinalIgnoreCase))
            {
                return "替我执行：低风险步骤自动推进，真实写图仍需确认。";
            }

            if (string.Equals(normalized, AgentApprovalFull, StringComparison.OrdinalIgnoreCase))
            {
                return "完全批准：尽量自动推进当前任务，高风险写图仍保留本地确认。";
            }

            return "请求批准：关键步骤前优先请求确认或补充信息。";
        }

        private static string GetConnectionModeShortName(string mode)
        {
            string normalized = NormalizeConnectionMode(mode);
            if (string.Equals(normalized, ConnectionModeService, StringComparison.OrdinalIgnoreCase))
            {
                return "智能体";
            }

            return "标准";
        }

        private static string GetConnectionModeDisplayName(string mode)
        {
            string normalized = NormalizeConnectionMode(mode);
            if (string.Equals(normalized, ConnectionModeService, StringComparison.OrdinalIgnoreCase))
            {
                return "智能体模式";
            }

            return "标准模式";
        }

        private static string BuildModeSwitchMessage(string mode)
        {
            string normalized = NormalizeConnectionMode(mode);
            if (string.Equals(normalized, ConnectionModeService, StringComparison.OrdinalIgnoreCase))
            {
                return "已切换到智能体模式。后续请求会通过 copilot backend 进行多步骤规划、预览，并按当前权限策略执行。";
            }

            return "已切换到标准模式。适合知识问答和单步骤图纸复核；复杂任务会建议切换智能体模式。";
        }

        private void LoadDirectSettingsForProvider()
        {
            string provider = GetSelectedProvider();
            DirectApiKeyBox.Text = GetDirectApiKey(provider);
            DirectModelBox.Text = GetConfiguredDirectModel(provider);
            DirectApiBaseUrlBox.Text = GetDirectApiBaseUrl(provider);
        }

        private void UpdateConfigEditorState()
        {
            bool useServiceMode = UseServiceMode();
            bool showOwnModelFields = true;
            string provider = GetSelectedProvider();
            string providerDisplay = GetProviderDisplayName(provider);

            if (ProviderRow == null || DirectApiKeyRow == null || DirectApiBaseUrlRow == null || DirectModelRow == null || ConfigHintText == null)
            {
                return;
            }

            ProviderRow.Visibility = showOwnModelFields ? Visibility.Visible : Visibility.Collapsed;
            DirectApiKeyRow.Visibility = showOwnModelFields ? Visibility.Visible : Visibility.Collapsed;
            DirectApiBaseUrlRow.Visibility = showOwnModelFields ? Visibility.Visible : Visibility.Collapsed;
            DirectModelRow.Visibility = showOwnModelFields ? Visibility.Visible : Visibility.Collapsed;
            if (AgentApprovalRow != null)
            {
                AgentApprovalRow.Visibility = useServiceMode ? Visibility.Visible : Visibility.Collapsed;
            }
            DirectApiKeyLabel.Text = providerDisplay + " API Key";
            DirectModelLabel.Text = providerDisplay + " 模型";
            if (useServiceMode && showOwnModelFields)
            {
                ConfigHintText.Text = "当前使用智能体模式。模型配置会随请求发送到 copilot backend，由连接器统一规划和转发。";
            }
            else if (useServiceMode)
            {
                ConfigHintText.Text = "当前使用智能体模式。服务地址可指向本地 127.0.0.1:8000 或远程 copilot backend。";
            }
            else
            {
                ConfigHintText.Text = "当前使用标准模式。可直接填写 " + providerDisplay + " API Key，并切换该供应商支持的模型。";
            }
            UpdateConnectionModeButtonVisual();
            UpdateFooterState();
        }

        private string GetConfiguredConnectionMode()
        {
            string configuredMode = NormalizeConnectionMode(Config.Get("CADCOPILOT_CONNECTION_MODE", string.Empty));
            if (!string.IsNullOrWhiteSpace(configuredMode))
            {
                return configuredMode;
            }

            return ConnectionModeStandard;
        }

        private string GetSelectedConnectionMode()
        {
            return GetComboBoxTag(ConnectionModeBox, GetConfiguredConnectionMode());
        }

        private string GetConfiguredProvider()
        {
            string provider = NormalizeProviderName(Config.Get("LLM_PROVIDER", ProviderMiniMax));
            if (string.IsNullOrWhiteSpace(provider))
            {
                return InferProviderFromModel(GetCurrentUiModel());
            }

            return provider;
        }

        private string GetSelectedProvider()
        {
            return GetComboBoxTag(ProviderBox, GetConfiguredProvider());
        }

        private string GetCurrentDirectModel()
        {
            DirectModelProfile activeProfile = GetActiveDirectProfile();
            if (activeProfile != null && !string.IsNullOrWhiteSpace(activeProfile.ModelName))
            {
                return activeProfile.ModelName;
            }

            string editorValue = DirectModelBox != null ? (DirectModelBox.Text ?? string.Empty).Trim() : string.Empty;
            return string.IsNullOrWhiteSpace(editorValue) ? GetCurrentUiModel() : editorValue;
        }

        private string GetCurrentServiceModel()
        {
            return Config.Get("CADCOPILOT_MODEL", GetCurrentUiModel());
        }

        private string GetConfiguredDirectModel(string provider)
        {
            return Config.Get("OPENAI_MODEL", GetDefaultDirectModel(provider));
        }

        private string GetDirectApiKey(string provider)
        {
            DirectModelProfile profile = FindAnyProfileForProvider(provider);
            if (profile != null && !string.IsNullOrWhiteSpace(profile.ApiKey))
            {
                return profile.ApiKey;
            }

            return Config.Get("OPENAI_API_KEY", string.Empty);
        }

        private string GetDirectApiBaseUrl(string provider)
        {
            DirectModelProfile profile = FindAnyProfileForProvider(provider);
            if (profile != null && !string.IsNullOrWhiteSpace(profile.ApiBaseUrl))
            {
                return profile.ApiBaseUrl;
            }

            return Config.Get("OPENAI_API_BASE_URL", GetProviderDefaultBaseUrl(provider));
        }

        private string[] GetDirectModelOptions(string provider)
        {
            return GetProviderModelOptions(provider);
        }

        private string[] GetDirectProfileModelNames()
        {
            List<string> modelNames = new List<string>();
            for (int i = 0; i < _directProfiles.Count; i++)
            {
                string modelName = (_directProfiles[i].ModelName ?? string.Empty).Trim();
                if (modelName.Length == 0)
                {
                    continue;
                }

                bool exists = false;
                for (int j = 0; j < modelNames.Count; j++)
                {
                    if (string.Equals(modelNames[j], modelName, StringComparison.OrdinalIgnoreCase))
                    {
                        exists = true;
                        break;
                    }
                }

                if (!exists)
                {
                    modelNames.Add(modelName);
                }
            }

            if (modelNames.Count == 0)
            {
                modelNames.Add(DefaultMiniMaxModel);
            }

            return modelNames.ToArray();
        }

        private string[] GetServiceProfileModelNames()
        {
            List<string> modelNames = new List<string>();
            for (int i = 0; i < _serviceProfiles.Count; i++)
            {
                string modelName = (_serviceProfiles[i].ModelName ?? string.Empty).Trim();
                if (modelName.Length == 0)
                {
                    continue;
                }

                bool exists = false;
                for (int j = 0; j < modelNames.Count; j++)
                {
                    if (string.Equals(modelNames[j], modelName, StringComparison.OrdinalIgnoreCase))
                    {
                        exists = true;
                        break;
                    }
                }

                if (!exists)
                {
                    modelNames.Add(modelName);
                }
            }

            if (modelNames.Count == 0)
            {
                modelNames.Add(DefaultServiceModel);
            }

            return modelNames.ToArray();
        }

        private string GetDefaultDirectModel(string provider)
        {
            ProviderDefinition definition = GetProviderDefinition(provider);
            return definition != null && definition.ModelOptions.Length > 0
                ? definition.ModelOptions[0]
                : DefaultMiniMaxModel;
        }

        private string GetDirectProviderDisplayName()
        {
            return GetProviderDisplayName(GetSelectedProvider());
        }

        private void LoadDirectProfiles()
        {
            string json = Config.Get("DIRECT_MODEL_PROFILES", string.Empty);
            List<DirectModelProfile> profiles = null;
            if (!string.IsNullOrWhiteSpace(json))
            {
                try
                {
                    profiles = JsonConvert.DeserializeObject<List<DirectModelProfile>>(json);
                }
                catch
                {
                    profiles = null;
                }
            }

            _directProfiles = profiles ?? new List<DirectModelProfile>();
            RemoveInvalidProfiles();
            if (_directProfiles.Count == 0)
            {
                _directProfiles.Add(CreateLegacyProfile());
                PersistDirectProfiles();
            }

            EnsureActiveDirectProfile();
        }

        private void LoadServiceProfiles()
        {
            string json = Config.Get("SERVICE_MODEL_PROFILES", string.Empty);
            List<ServiceModelProfile> profiles = null;
            if (!string.IsNullOrWhiteSpace(json))
            {
                try
                {
                    profiles = JsonConvert.DeserializeObject<List<ServiceModelProfile>>(json);
                }
                catch
                {
                    profiles = null;
                }
            }

            _serviceProfiles = profiles ?? CreateDefaultServiceProfiles();
            RemoveInvalidServiceProfiles();
            if (_serviceProfiles.Count == 0)
            {
                _serviceProfiles = CreateDefaultServiceProfiles();
                PersistServiceProfiles();
            }

            EnsureActiveServiceProfile();
        }

        private void PersistDirectProfiles()
        {
            Config.Set("DIRECT_MODEL_PROFILES", JsonConvert.SerializeObject(_directProfiles, Formatting.None));
        }

        private void PersistServiceProfiles()
        {
            Config.Set("SERVICE_MODEL_PROFILES", JsonConvert.SerializeObject(_serviceProfiles, Formatting.None));
        }

        private void RemoveInvalidProfiles()
        {
            for (int i = _directProfiles.Count - 1; i >= 0; i--)
            {
                DirectModelProfile profile = _directProfiles[i];
                if (string.IsNullOrWhiteSpace(profile.ModelName))
                {
                    _directProfiles.RemoveAt(i);
                    continue;
                }

                profile.Provider = NormalizeProviderName(profile.Provider);
                if (string.IsNullOrWhiteSpace(profile.Provider))
                {
                    profile.Provider = InferProviderFromModel(profile.ModelName);
                }

                if (string.IsNullOrWhiteSpace(profile.ApiBaseUrl))
                {
                    profile.ApiBaseUrl = GetProviderDefaultBaseUrl(profile.Provider);
                }

                if (string.Equals(profile.ModelName, "claude-sonnet-4-20250514", StringComparison.OrdinalIgnoreCase))
                {
                    profile.Provider = ProviderMiniMax;
                    profile.ModelName = DefaultMiniMaxModel;
                    profile.ApiBaseUrl = GetProviderDefaultBaseUrl(profile.Provider);
                }
            }
        }

        private void RemoveInvalidServiceProfiles()
        {
            for (int i = _serviceProfiles.Count - 1; i >= 0; i--)
            {
                if (string.IsNullOrWhiteSpace(_serviceProfiles[i].ModelName))
                {
                    _serviceProfiles.RemoveAt(i);
                }
            }
        }

        private DirectModelProfile CreateLegacyProfile()
        {
            string configuredModel = Config.Get("OPENAI_MODEL", Config.Get("CADCOPILOT_MODEL", DefaultMiniMaxModel));
            string provider = NormalizeProviderName(Config.Get("LLM_PROVIDER", InferProviderFromModel(configuredModel)));
            return new DirectModelProfile
            {
                ModelName = string.IsNullOrWhiteSpace(configuredModel) ? GetDefaultDirectModel(provider) : configuredModel,
                ApiKey = GetDirectApiKey(provider),
                Provider = provider,
                ApiBaseUrl = Config.Get("OPENAI_API_BASE_URL", GetProviderDefaultBaseUrl(provider))
            };
        }

        private List<ServiceModelProfile> CreateDefaultServiceProfiles()
        {
            List<ServiceModelProfile> profiles = new List<ServiceModelProfile>();
            string[] options = GetKnownModelOptions();
            for (int i = 0; i < options.Length; i++)
            {
                profiles.Add(new ServiceModelProfile { ModelName = options[i] });
            }

            string configuredModel = Config.Get("CADCOPILOT_MODEL", DefaultMiniMaxModel);
            if (FindServiceProfile(configuredModel, profiles) == null)
            {
                profiles.Insert(0, new ServiceModelProfile { ModelName = configuredModel });
            }

            return profiles;
        }

        private DirectModelProfile CreateDefaultProfile()
        {
            return new DirectModelProfile
            {
                ModelName = DefaultMiniMaxModel,
                ApiKey = string.Empty,
                Provider = ProviderMiniMax,
                ApiBaseUrl = DefaultMiniMaxBaseUrl
            };
        }

        private void EnsureActiveDirectProfile()
        {
            DirectModelProfile activeProfile = GetActiveDirectProfile();
            if (activeProfile == null && _directProfiles.Count > 0)
            {
                activeProfile = _directProfiles[0];
            }

            if (activeProfile != null)
            {
                ApplyDirectProfile(activeProfile);
            }
        }

        private void EnsureActiveServiceProfile()
        {
            ServiceModelProfile activeProfile = GetActiveServiceProfile();
            if (activeProfile == null && _serviceProfiles.Count > 0)
            {
                activeProfile = _serviceProfiles[0];
            }

            if (activeProfile != null)
            {
                ApplyServiceProfile(activeProfile);
            }
        }

        private DirectModelProfile GetActiveDirectProfile()
        {
            string activeModel = Config.Get("ACTIVE_DIRECT_MODEL", string.Empty);
            if (!string.IsNullOrWhiteSpace(activeModel))
            {
                return FindDirectProfile(activeModel);
            }

            string currentModel = GetCurrentUiModel();
            DirectModelProfile currentProfile = FindDirectProfile(currentModel);
            return currentProfile ?? (_directProfiles.Count > 0 ? _directProfiles[0] : null);
        }

        private ServiceModelProfile GetActiveServiceProfile()
        {
            string activeModel = Config.Get("ACTIVE_SERVICE_MODEL", string.Empty);
            if (!string.IsNullOrWhiteSpace(activeModel))
            {
                return FindServiceProfile(activeModel);
            }

            string currentModel = Config.Get("CADCOPILOT_MODEL", DefaultMiniMaxModel);
            ServiceModelProfile currentProfile = FindServiceProfile(currentModel);
            return currentProfile ?? (_serviceProfiles.Count > 0 ? _serviceProfiles[0] : null);
        }

        private DirectModelProfile FindDirectProfile(string modelName)
        {
            for (int i = 0; i < _directProfiles.Count; i++)
            {
                if (string.Equals(_directProfiles[i].ModelName, modelName, StringComparison.OrdinalIgnoreCase))
                {
                    return _directProfiles[i];
                }
            }

            return null;
        }

        private ServiceModelProfile FindServiceProfile(string modelName)
        {
            return FindServiceProfile(modelName, _serviceProfiles);
        }

        private static ServiceModelProfile FindServiceProfile(string modelName, List<ServiceModelProfile> profiles)
        {
            if (profiles == null)
            {
                return null;
            }

            for (int i = 0; i < profiles.Count; i++)
            {
                if (string.Equals(profiles[i].ModelName, modelName, StringComparison.OrdinalIgnoreCase))
                {
                    return profiles[i];
                }
            }

            return null;
        }

        private void ApplyServiceProfile(ServiceModelProfile profile)
        {
            if (profile == null)
            {
                return;
            }

            Config.Set("ACTIVE_SERVICE_MODEL", profile.ModelName);
            Config.Set("CADCOPILOT_MODEL", profile.ModelName);
            Config.Set("ACTIVE_DIRECT_MODEL", profile.ModelName);
        }

        private void ApplyDirectProfile(DirectModelProfile profile)
        {
            if (profile == null)
            {
                return;
            }

            string provider = NormalizeProviderName(profile.Provider);
            Config.SetMany(
                new KeyValuePair<string, string>("ACTIVE_DIRECT_MODEL", profile.ModelName),
                new KeyValuePair<string, string>("ACTIVE_SERVICE_MODEL", profile.ModelName),
                new KeyValuePair<string, string>("CADCOPILOT_MODEL", profile.ModelName),
                new KeyValuePair<string, string>("LLM_PROVIDER", provider),
                new KeyValuePair<string, string>("OPENAI_MODEL", profile.ModelName),
                new KeyValuePair<string, string>("OPENAI_API_KEY", profile.ApiKey ?? string.Empty),
                new KeyValuePair<string, string>("OPENAI_API_BASE_URL", string.IsNullOrWhiteSpace(profile.ApiBaseUrl) ? GetProviderDefaultBaseUrl(provider) : profile.ApiBaseUrl)
            );

            bool previousLoading = _isLoadingSettings;
            _isLoadingSettings = true;
            _isUpdatingProfileSelectors = true;
            try
            {
                SelectComboBoxTag(ProviderBox, provider);
                SelectComboBoxTag(ProfileProviderBox, provider);
                PopulateProfileModelOptions(provider, profile.ModelName);
                if (ProfileProviderButtonText != null)
                {
                    ProfileProviderButtonText.Text = GetProviderDisplayName(provider);
                }

                if (ProfileModelNameButtonText != null)
                {
                    ProfileModelNameButtonText.Text = profile.ModelName;
                }

                DirectModelBox.Text = profile.ModelName;
                DirectApiKeyBox.Text = profile.ApiKey ?? string.Empty;
                DirectApiBaseUrlBox.Text = string.IsNullOrWhiteSpace(profile.ApiBaseUrl) ? GetProviderDefaultBaseUrl(provider) : profile.ApiBaseUrl;
            }
            finally
            {
                _isUpdatingProfileSelectors = false;
                _isLoadingSettings = previousLoading;
            }
        }

        private void LoadProfileEditor(DirectModelProfile profile)
        {
            DirectModelProfile effectiveProfile = profile ?? FindDirectProfile(GetCurrentUiModel()) ?? CreateSuggestedProfile(GetCurrentUiModel()) ?? CreateLegacyProfile();
            string provider = NormalizeProviderName(effectiveProfile.Provider);
            ApplyProfileEditorSelection(provider, effectiveProfile.ModelName ?? string.Empty, effectiveProfile.ApiKey ?? string.Empty, true);
            ProfileApiKeyBox.Text = string.Empty;
            InvalidateProfileValidation("请先测试连接，成功后才能保存。");
            UpdateProfileEditorState();
        }

        private void LoadServiceProfileEditor(ServiceModelProfile profile)
        {
            ServiceModelProfile effectiveProfile = profile ?? GetActiveServiceProfile() ?? new ServiceModelProfile { ModelName = DefaultServiceModel };
            ProfileModelNameBox.Text = effectiveProfile.ModelName ?? string.Empty;
            ProfileApiKeyBox.Text = string.Empty;
            InvalidateProfileValidation("请先测试连接，成功后才能保存。");
            UpdateProfileEditorState();
        }

        private void LoadProfileEditorForCurrentMode()
        {
            LoadProfileEditor(FindDirectProfile(GetCurrentUiModel()));
        }

        private void UpdateProfileEditorState()
        {
            string provider = GetComboBoxTag(ProfileProviderBox, ProviderMiniMax);
            bool isOfficialProvider = IsOfficialProvider(provider);
            ProfileDialogTitleText.Text = "模型设置";
            ProfileProviderRow.Visibility = Visibility.Visible;
            ProfileApiKeyRow.Visibility = isOfficialProvider ? Visibility.Collapsed : Visibility.Visible;
            ProfileModelNameLabel.Text = "模型名称";
            ProfileApiKeyLabel.Text = isOfficialProvider ? "官方服务" : "API Key";
        }

        private void ProfileProviderBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            if (_isLoadingSettings || _isUpdatingProfileSelectors)
            {
                return;
            }

            string provider = GetComboBoxTag(ProfileProviderBox, ProviderMiniMax);
            DirectModelProfile profile = FindAnyProfileForProvider(provider);
            string targetModel = profile != null ? profile.ModelName : GetDefaultDirectModel(provider);
            ApplyProfileEditorSelection(provider, targetModel, profile != null ? profile.ApiKey ?? string.Empty : string.Empty, false);
            InvalidateProfileValidation("提供商已变更，请重新测试连接。");
        }

        private void ProfileModelNameBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            if (_isLoadingSettings || _isUpdatingProfileSelectors)
            {
                return;
            }

            string modelName = GetSelectedComboBoxText(ProfileModelNameBox).Trim();
            if (!string.IsNullOrWhiteSpace(modelName))
            {
                SetProfileModelSelection(modelName, false);
                InvalidateProfileValidation("模型已变更，请重新测试连接。");
            }
        }

        private void ProfileApiKeyBox_TextChanged(object sender, TextChangedEventArgs e)
        {
            if (_isLoadingSettings || _isUpdatingProfileSelectors)
            {
                return;
            }

            InvalidateProfileValidation("API Key 已变更，请重新测试连接。");
        }

        private void ProfileProviderButton_Click(object sender, RoutedEventArgs e)
        {
            BuildProfileProviderOptionsPopup();
            if (ProfileModelNamePopup != null)
            {
                ProfileModelNamePopup.IsOpen = false;
            }

            ProfileProviderPopup.IsOpen = !ProfileProviderPopup.IsOpen;
        }

        private void ProfileModelNameButton_Click(object sender, RoutedEventArgs e)
        {
            BuildProfileModelNameOptionsPopup();
            if (ProfileProviderPopup != null)
            {
                ProfileProviderPopup.IsOpen = false;
            }

            ProfileModelNamePopup.IsOpen = !ProfileModelNamePopup.IsOpen;
        }

        private void SaveProfile_Click(object sender, RoutedEventArgs e)
        {
            string provider = GetComboBoxTag(ProfileProviderBox, ProviderMiniMax);
            string modelName = (ProfileModelNameBox.Text ?? string.Empty).Trim();
            string apiKey = GetEffectiveProfileApiKey(provider, modelName);
            bool isOfficialProvider = IsOfficialProvider(provider);
            if (string.IsNullOrWhiteSpace(modelName))
            {
                SetStatus("模型名不能为空");
                SetProfileActionStatus("模型名不能为空");
                return;
            }

            if (isOfficialProvider)
            {
                apiKey = string.Empty;
            }

            if (!IsCurrentProfileValidationAccepted(provider, modelName, apiKey))
            {
                InvalidateProfileValidation("请先测试连接成功，再保存当前配置。");
                return;
            }

            string apiBaseUrl = GetEffectiveProfileApiBaseUrl(provider, modelName);
            if (isOfficialProvider)
            {
                apiBaseUrl = string.Empty;
            }
            DirectModelProfile profile = UpsertDirectProfile(modelName, provider, apiKey, apiBaseUrl);

            SetStatus("保存模型中");
            SetProfileActionStatus("保存中...");
            SaveProfileButton.IsEnabled = false;
            TestConnectionButton.IsEnabled = false;
            if (ProfileProviderPopup != null)
            {
                ProfileProviderPopup.IsOpen = false;
            }

            if (ProfileModelNamePopup != null)
            {
                ProfileModelNamePopup.IsOpen = false;
            }

            PersistDirectProfiles();
            ApplyDirectProfile(profile);
            ReloadClient();
            RefreshModelSelector();
            ModelSelector.SelectedItem = modelName;
            HeaderSettingsPopup.IsOpen = false;
            SetStatus("模型已保存");
            SetProfileActionStatus("模型已保存");
            ProfileApiKeyBox.Text = string.Empty;
            ClearProfileValidation();
            SaveProfileButton.IsEnabled = true;
            TestConnectionButton.IsEnabled = true;
        }

        private void SaveServiceProfile()
        {
            string modelName = (ProfileModelNameBox.Text ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(modelName))
            {
                SetStatus("模型名不能为空");
                return;
            }

            ServiceModelProfile profile = FindServiceProfile(modelName);
            if (profile == null)
            {
                profile = new ServiceModelProfile { ModelName = modelName };
                _serviceProfiles.Add(profile);
            }
            else
            {
                profile.ModelName = modelName;
            }

            PersistServiceProfiles();
            ApplyServiceProfile(profile);
            ReloadClient();
            RefreshModelSelector();
            ModelSelector.SelectedItem = modelName;
            HeaderSettingsPopup.IsOpen = false;
            SetStatus("代理模型已保存");
            AddMessage("system", "代理模型已保存并记住。现在可以在模型选择器中切换 “" + modelName + "”。");
        }

        private void DeleteProfile_Click(object sender, RoutedEventArgs e)
        {
            string modelName = (ProfileModelNameBox.Text ?? string.Empty).Trim();
            DirectModelProfile profile = FindDirectProfile(modelName);
            ServiceModelProfile serviceProfile = FindServiceProfile(modelName);
            if (profile == null && serviceProfile == null)
            {
                return;
            }

            if (profile != null)
            {
                _directProfiles.Remove(profile);
            }

            if (serviceProfile != null)
            {
                _serviceProfiles.Remove(serviceProfile);
            }

            if (_directProfiles.Count == 0)
            {
                _directProfiles.Add(CreateDefaultProfile());
            }

            PersistDirectProfiles();
            PersistServiceProfiles();
            EnsureActiveDirectProfile();
            ReloadClient();
            RefreshModelSelector();
            LoadProfileEditor(FindDirectProfile(GetCurrentUiModel()));
            SetStatus("模型已删除");
        }

        private void DeleteServiceProfile()
        {
            string modelName = (ProfileModelNameBox.Text ?? string.Empty).Trim();
            ServiceModelProfile profile = FindServiceProfile(modelName);
            if (profile == null)
            {
                return;
            }

            _serviceProfiles.Remove(profile);
            if (_serviceProfiles.Count == 0)
            {
                _serviceProfiles = CreateDefaultServiceProfiles();
            }

            PersistServiceProfiles();
            EnsureActiveServiceProfile();
            ReloadClient();
            RefreshModelSelector();
            LoadServiceProfileEditor(GetActiveServiceProfile());
            SetStatus("代理模型已删除");
        }

        private async void TestConnection_Click(object sender, RoutedEventArgs e)
        {
            if (_isBusy)
            {
                return;
            }

            string provider = GetComboBoxTag(ProfileProviderBox, ProviderMiniMax);
            string model = (ProfileModelNameBox.Text ?? string.Empty).Trim();
            string apiKey = GetEffectiveProfileApiKey(provider, model);
            string apiBaseUrl = GetEffectiveProfileApiBaseUrl(provider, model);
            bool isOfficialProvider = IsOfficialProvider(provider);
            if (string.IsNullOrWhiteSpace(model))
            {
                SetProfileActionStatus("请先选择模型。");
                return;
            }

            if (ProviderRequiresApiKey(provider) && string.IsNullOrWhiteSpace(apiKey))
            {
                InvalidateProfileValidation("请先输入 API Key，再测试连接。");
                return;
            }

            try
            {
                if (ProfileProviderPopup != null)
                {
                    ProfileProviderPopup.IsOpen = false;
                }

                if (ProfileModelNamePopup != null)
                {
                    ProfileModelNamePopup.IsOpen = false;
                }

                TestConnectionButton.IsEnabled = false;
                SaveProfileButton.IsEnabled = false;
                SetStatus("测试连接中");
                SetProfileActionStatus("测试连接中...");
                string result = await ClaudeClient.TestDirectConnectionAsync(provider, model, apiKey, apiBaseUrl);
                ApplyEditorValuesToRuntime();
                ReloadClient();
                SetStatus("连接测试成功");
                SetProfileValidationSuccess(provider, model, apiKey);
                SetProfileActionStatus("连接成功，可以保存。" + (string.IsNullOrWhiteSpace(result) ? string.Empty : " " + result));
            }
            catch (Exception ex)
            {
                Exception baseException = ex.GetBaseException();
                Logger.Error("Direct connection test failed. Provider=" + provider
                    + ", Model=" + model
                    + ", BaseUrl=" + apiBaseUrl
                    + ", Error=" + ex);
                SetStatus("连接测试失败");
                ClearProfileValidation();
                SetProfileActionStatus("失败: " + (baseException != null && !string.IsNullOrWhiteSpace(baseException.Message) ? baseException.Message : ex.Message));
            }
            finally
            {
                TestConnectionButton.IsEnabled = true;
                SaveProfileButton.IsEnabled = IsCurrentProfileValidationAccepted(provider, model, apiKey);
            }
        }

        private void ApplyEditorValuesToRuntime()
        {
            string provider = GetComboBoxTag(ProfileProviderBox, ProviderMiniMax);
            string model = (ProfileModelNameBox.Text ?? string.Empty).Trim();
            string apiKey = GetEffectiveProfileApiKey(provider, model);
            string apiBaseUrl = GetEffectiveProfileApiBaseUrl(provider, model);
            if (IsOfficialProvider(provider))
            {
                apiKey = string.Empty;
                apiBaseUrl = string.Empty;
            }
            if (string.IsNullOrWhiteSpace(model))
            {
                throw new InvalidOperationException("请先填写模型名称。\n测试连接前需要可用的模型名。");
            }

            Config.SetMany(
                new KeyValuePair<string, string>("LLM_PROVIDER", provider),
                new KeyValuePair<string, string>("ACTIVE_DIRECT_MODEL", model),
                new KeyValuePair<string, string>("ACTIVE_SERVICE_MODEL", model),
                new KeyValuePair<string, string>("CADCOPILOT_MODEL", model),
                new KeyValuePair<string, string>("OPENAI_MODEL", model),
                new KeyValuePair<string, string>("OPENAI_API_KEY", apiKey),
                new KeyValuePair<string, string>("OPENAI_API_BASE_URL", apiBaseUrl)
            );
        }

        private void InvalidateProfileValidation(string reason)
        {
            ClearProfileValidation();
            SaveProfileButton.IsEnabled = false;
            SetProfileActionStatus(reason);
        }

        private void ClearProfileValidation()
        {
            _profileValidatedProvider = null;
            _profileValidatedModel = null;
            _profileValidatedApiKey = null;
        }

        private void SetProfileValidationSuccess(string provider, string model, string apiKey)
        {
            _profileValidatedProvider = NormalizeProviderName(provider);
            _profileValidatedModel = (model ?? string.Empty).Trim();
            _profileValidatedApiKey = apiKey ?? string.Empty;
            SaveProfileButton.IsEnabled = true;
        }

        private bool IsCurrentProfileValidationAccepted(string provider, string model, string apiKey)
        {
            if (IsOfficialProvider(provider))
            {
                return string.Equals(_profileValidatedProvider, NormalizeProviderName(provider), StringComparison.OrdinalIgnoreCase)
                       && string.Equals(_profileValidatedModel, (model ?? string.Empty).Trim(), StringComparison.OrdinalIgnoreCase);
            }

            return string.Equals(_profileValidatedProvider, NormalizeProviderName(provider), StringComparison.OrdinalIgnoreCase)
                   && string.Equals(_profileValidatedModel, (model ?? string.Empty).Trim(), StringComparison.OrdinalIgnoreCase)
                   && string.Equals(_profileValidatedApiKey ?? string.Empty, apiKey ?? string.Empty, StringComparison.Ordinal);
        }

        private string GetEffectiveProfileApiKey(string provider, string modelName)
        {
            string enteredApiKey = ProfileApiKeyBox != null ? (ProfileApiKeyBox.Text ?? string.Empty).Trim() : string.Empty;
            if (!string.IsNullOrWhiteSpace(enteredApiKey))
            {
                return enteredApiKey;
            }

            DirectModelProfile exactProfile = FindDirectProfile(modelName);
            if (exactProfile != null && !string.IsNullOrWhiteSpace(exactProfile.ApiKey))
            {
                return exactProfile.ApiKey;
            }

            DirectModelProfile providerProfile = FindAnyProfileForProvider(provider);
            return providerProfile != null ? providerProfile.ApiKey ?? string.Empty : string.Empty;
        }

        private string GetEffectiveProfileApiBaseUrl(string provider, string modelName)
        {
            string enteredApiBaseUrl = DirectApiBaseUrlBox != null ? (DirectApiBaseUrlBox.Text ?? string.Empty).Trim() : string.Empty;
            if (!string.IsNullOrWhiteSpace(enteredApiBaseUrl))
            {
                return enteredApiBaseUrl;
            }

            DirectModelProfile exactProfile = FindDirectProfile(modelName);
            if (exactProfile != null && !string.IsNullOrWhiteSpace(exactProfile.ApiBaseUrl))
            {
                return exactProfile.ApiBaseUrl;
            }

            DirectModelProfile providerProfile = FindAnyProfileForProvider(provider);
            if (providerProfile != null && !string.IsNullOrWhiteSpace(providerProfile.ApiBaseUrl))
            {
                return providerProfile.ApiBaseUrl;
            }

            return Config.Get("OPENAI_API_BASE_URL", GetProviderDefaultBaseUrl(provider));
        }

        private void SetProfileActionStatus(string message)
        {
            if (ProfileActionStatusText == null)
            {
                return;
            }

            ProfileActionStatusText.Text = message ?? string.Empty;
        }

        private void CloseModelSettings_Click(object sender, RoutedEventArgs e)
        {
            if (ProfileProviderPopup != null)
            {
                ProfileProviderPopup.IsOpen = false;
            }

            if (ProfileModelNamePopup != null)
            {
                ProfileModelNamePopup.IsOpen = false;
            }

            HeaderSettingsPopup.IsOpen = false;
        }

        private static ProviderDefinition GetProviderDefinition(string provider)
        {
            string normalized = NormalizeProviderName(provider);
            for (int i = 0; i < SupportedProviders.Length; i++)
            {
                if (string.Equals(SupportedProviders[i].Key, normalized, StringComparison.OrdinalIgnoreCase))
                {
                    return SupportedProviders[i];
                }
            }

            return SupportedProviders[0];
        }

        private static string GetProviderDisplayName(string provider)
        {
            return GetProviderDefinition(provider).DisplayName;
        }

        private static string GetProviderDefaultBaseUrl(string provider)
        {
            return GetProviderDefinition(provider).DefaultBaseUrl;
        }

        private static string[] GetProviderModelOptions(string provider)
        {
            return GetProviderDefinition(provider).ModelOptions;
        }

        private static string[] GetKnownModelOptions()
        {
            List<string> models = new List<string>();
            for (int i = 0; i < SupportedProviders.Length; i++)
            {
                string[] modelOptions = SupportedProviders[i].ModelOptions;
                for (int j = 0; j < modelOptions.Length; j++)
                {
                    if (!models.Contains(modelOptions[j]))
                    {
                        models.Add(modelOptions[j]);
                    }
                }
            }

            return models.ToArray();
        }

        private static string InferProviderFromModel(string modelName)
        {
            string normalized = (modelName ?? string.Empty).Trim().ToLowerInvariant();
            if (normalized.StartsWith("cadcopilot", StringComparison.OrdinalIgnoreCase) || normalized.StartsWith("cad-copilot", StringComparison.OrdinalIgnoreCase))
            {
                return ProviderCadCopilot;
            }

            if (normalized.StartsWith("gpt", StringComparison.OrdinalIgnoreCase))
            {
                return ProviderOpenAi;
            }

            if (normalized.StartsWith("deepseek", StringComparison.OrdinalIgnoreCase))
            {
                return ProviderDeepSeek;
            }

            if (normalized.StartsWith("claude", StringComparison.OrdinalIgnoreCase))
            {
                return ProviderAnthropic;
            }

            if (normalized.StartsWith("qwen", StringComparison.OrdinalIgnoreCase) ||
                normalized.StartsWith("llama", StringComparison.OrdinalIgnoreCase))
            {
                return ProviderOllama;
            }

            return ProviderMiniMax;
        }

        private static string GetProviderAccentColor(string provider)
        {
            string normalized = NormalizeProviderName(provider);
            if (string.Equals(normalized, ProviderCadCopilot, StringComparison.OrdinalIgnoreCase))
            {
                return "#C586C0";
            }

            if (string.Equals(normalized, ProviderOpenAi, StringComparison.OrdinalIgnoreCase))
            {
                return "#58A6FF";
            }

            if (string.Equals(normalized, ProviderDeepSeek, StringComparison.OrdinalIgnoreCase))
            {
                return "#D7BA7D";
            }

            return "#4EC9B0";
        }

        private string GetCurrentUiModel()
        {
            string activeModel = Config.Get("ACTIVE_DIRECT_MODEL", string.Empty);
            if (!string.IsNullOrWhiteSpace(activeModel))
            {
                return activeModel;
            }

            activeModel = Config.Get("ACTIVE_SERVICE_MODEL", string.Empty);
            if (!string.IsNullOrWhiteSpace(activeModel))
            {
                return activeModel;
            }

            activeModel = Config.Get("CADCOPILOT_MODEL", string.Empty);
            if (!string.IsNullOrWhiteSpace(activeModel))
            {
                return activeModel;
            }

            activeModel = Config.Get("OPENAI_MODEL", string.Empty);
            return string.IsNullOrWhiteSpace(activeModel) ? DefaultMiniMaxModel : activeModel;
        }

        private string[] GetUnifiedModelNames()
        {
            List<string> modelNames = new List<string>();
            for (int i = 0; i < _directProfiles.Count; i++)
            {
                string modelName = (_directProfiles[i].ModelName ?? string.Empty).Trim();
                if (modelName.Length > 0 && !modelNames.Exists(item => string.Equals(item, modelName, StringComparison.OrdinalIgnoreCase)))
                {
                    modelNames.Add(modelName);
                }
            }

            string currentModel = GetCurrentUiModel();
            if (!string.IsNullOrWhiteSpace(currentModel) && !modelNames.Exists(item => string.Equals(item, currentModel, StringComparison.OrdinalIgnoreCase)))
            {
                DirectModelProfile currentProfile = CreateSuggestedProfile(currentModel);
                _directProfiles.Insert(0, currentProfile);
                PersistDirectProfiles();
                modelNames.Insert(0, currentProfile.ModelName);
            }

            if (modelNames.Count == 0)
            {
                DirectModelProfile fallbackProfile = CreateDefaultProfile();
                _directProfiles.Add(fallbackProfile);
                PersistDirectProfiles();
                modelNames.Add(fallbackProfile.ModelName);
            }

            return modelNames.ToArray();
        }

        private string BuildModelSelectorSuffix(string option, string currentModel)
        {
            DirectModelProfile profile = FindDirectProfile(option);
            if (profile == null)
            {
                return string.Empty;
            }

            if (IsOfficialProvider(profile.Provider))
            {
                return string.Equals(option, currentModel, StringComparison.OrdinalIgnoreCase) ? "官方服务 / 当前" : "官方服务";
            }

            string status = string.IsNullOrWhiteSpace(profile.ApiKey) ? "未连接" : "已配置";
            if (string.Equals(option, currentModel, StringComparison.OrdinalIgnoreCase))
            {
                return status + " / 当前";
            }

            return status;
        }

        private DirectModelProfile FindAnyProfileForProvider(string provider)
        {
            string normalized = NormalizeProviderName(provider);
            for (int i = 0; i < _directProfiles.Count; i++)
            {
                if (string.Equals(NormalizeProviderName(_directProfiles[i].Provider), normalized, StringComparison.OrdinalIgnoreCase))
                {
                    return _directProfiles[i];
                }
            }

            return null;
        }

        private DirectModelProfile CreateSuggestedProfile(string modelName)
        {
            string normalizedModel = (modelName ?? string.Empty).Trim();
            string provider = InferProviderFromModel(normalizedModel);
            DirectModelProfile profile = FindAnyProfileForProvider(provider);
            return new DirectModelProfile
            {
                ModelName = string.IsNullOrWhiteSpace(normalizedModel) ? GetDefaultDirectModel(provider) : normalizedModel,
                Provider = provider,
                ApiKey = profile != null ? profile.ApiKey ?? string.Empty : string.Empty,
                ApiBaseUrl = profile != null && !string.IsNullOrWhiteSpace(profile.ApiBaseUrl) ? profile.ApiBaseUrl : GetProviderDefaultBaseUrl(provider)
            };
        }

        private DirectModelProfile UpsertDirectProfile(string modelName, string provider, string apiKey, string apiBaseUrl)
        {
            DirectModelProfile profile = FindDirectProfile(modelName);
            if (profile == null)
            {
                profile = new DirectModelProfile();
                _directProfiles.Add(profile);
            }

            profile.ModelName = modelName;
            profile.Provider = NormalizeProviderName(provider);
            profile.ApiKey = apiKey ?? string.Empty;
            profile.ApiBaseUrl = string.IsNullOrWhiteSpace(apiBaseUrl) ? GetProviderDefaultBaseUrl(profile.Provider) : apiBaseUrl;
            return profile;
        }

        private void ApplyModelSelection(string model)
        {
            DirectModelProfile profile = FindDirectProfile(model);
            if (profile == null)
            {
                profile = CreateSuggestedProfile(model);
                _directProfiles.Add(profile);
                PersistDirectProfiles();
            }

            Config.Set("ACTIVE_DIRECT_MODEL", profile.ModelName);
            Config.Set("ACTIVE_SERVICE_MODEL", profile.ModelName);
            Config.Set("CADCOPILOT_MODEL", profile.ModelName);
            ApplyDirectProfile(profile);
            LoadProfileEditor(profile);
        }

        private void PopulateProfileModelOptions(string provider, string selectedModel)
        {
            if (ProfileModelNameBox == null)
            {
                return;
            }

            string normalizedProvider = NormalizeProviderName(provider);
            string currentValue = string.IsNullOrWhiteSpace(selectedModel) ? GetDefaultDirectModel(normalizedProvider) : selectedModel.Trim();
            ProfileModelNameBox.Items.Clear();

            string[] options = GetProviderModelOptions(normalizedProvider);
            for (int i = 0; i < options.Length; i++)
            {
                ProfileModelNameBox.Items.Add(options[i]);
            }

            if (!ProfileModelNameBox.Items.Contains(currentValue))
            {
                ProfileModelNameBox.Items.Add(currentValue);
            }

            ProfileModelNameBox.SelectedItem = currentValue;
            ProfileModelNameBox.Text = currentValue;
        }

        private void ApplyProfileEditorSelection(string provider, string modelName, string apiKey, bool syncProviderSelection)
        {
            string normalizedProvider = NormalizeProviderName(provider);
            string targetModel = string.IsNullOrWhiteSpace(modelName) ? GetDefaultDirectModel(normalizedProvider) : modelName.Trim();

            _isUpdatingProfileSelectors = true;
            try
            {
                if (syncProviderSelection)
                {
                    SelectComboBoxTag(ProfileProviderBox, normalizedProvider);
                }

                PopulateProfileModelOptions(normalizedProvider, targetModel);
                if (ProfileApiKeyBox != null)
                {
                    ProfileApiKeyBox.Text = string.Empty;
                }
                if (ProfileProviderButtonText != null)
                {
                    ProfileProviderButtonText.Text = GetProviderDisplayName(normalizedProvider);
                }

                if (ProfileModelNameButtonText != null)
                {
                    ProfileModelNameButtonText.Text = targetModel;
                }
            }
            finally
            {
                _isUpdatingProfileSelectors = false;
            }

            BuildProfileProviderOptionsPopup();
            BuildProfileModelNameOptionsPopup();
            UpdateProfileEditorState();
        }

        private void SetProfileModelSelection(string modelName, bool syncHiddenSelection)
        {
            string targetModel = (modelName ?? string.Empty).Trim();
            if (targetModel.Length == 0)
            {
                return;
            }

            _isUpdatingProfileSelectors = true;
            try
            {
                if (syncHiddenSelection && ProfileModelNameBox != null)
                {
                    bool contains = ProfileModelNameBox.Items.Contains(targetModel);
                    if (!contains)
                    {
                        ProfileModelNameBox.Items.Add(targetModel);
                    }

                    ProfileModelNameBox.SelectedItem = targetModel;
                    ProfileModelNameBox.Text = targetModel;
                }

                if (ProfileModelNameButtonText != null)
                {
                    ProfileModelNameButtonText.Text = targetModel;
                }
            }
            finally
            {
                _isUpdatingProfileSelectors = false;
            }

            BuildProfileModelNameOptionsPopup();
        }

        private void BuildProfileProviderOptionsPopup()
        {
            if (ProfileProviderOptionsPanel == null)
            {
                return;
            }

            string currentProvider = GetComboBoxTag(ProfileProviderBox, ProviderMiniMax);
            ProfileProviderOptionsPanel.Children.Clear();
            for (int i = 0; i < SupportedProviders.Length; i++)
            {
                ProviderDefinition definition = SupportedProviders[i];
                ProfileProviderOptionsPanel.Children.Add(CreateSelectorPopupButton(
                    definition.DisplayName,
                    string.Equals(definition.Key, currentProvider, StringComparison.OrdinalIgnoreCase) ? "当前" : string.Empty,
                    definition.Key,
                    ProfileProviderOption_Click));
            }
        }

        private void BuildProfileModelNameOptionsPopup()
        {
            if (ProfileModelNameOptionsPanel == null)
            {
                return;
            }

            string provider = GetComboBoxTag(ProfileProviderBox, ProviderMiniMax);
            string currentModel = (ProfileModelNameBox != null ? ProfileModelNameBox.Text : string.Empty) ?? string.Empty;
            string[] options = GetProviderModelOptions(provider);
            List<string> modelNames = new List<string>();
            for (int i = 0; i < options.Length; i++)
            {
                if (!modelNames.Contains(options[i]))
                {
                    modelNames.Add(options[i]);
                }
            }

            if (!string.IsNullOrWhiteSpace(currentModel) && !modelNames.Contains(currentModel))
            {
                modelNames.Add(currentModel);
            }

            ProfileModelNameOptionsPanel.Children.Clear();
            for (int i = 0; i < modelNames.Count; i++)
            {
                string option = modelNames[i];
                ProfileModelNameOptionsPanel.Children.Add(CreateSelectorPopupButton(
                    option,
                    string.Equals(option, currentModel, StringComparison.OrdinalIgnoreCase) ? "当前" : string.Empty,
                    option,
                    ProfileModelOption_Click));
            }
        }

        private Button CreateSelectorPopupButton(string label, string suffix, object tag, RoutedEventHandler clickHandler)
        {
            Button button = new Button
            {
                Tag = tag,
                Style = (Style)FindResource("PopupMenuItemButtonStyle")
            };

            Grid layout = new Grid();
            layout.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            layout.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            TextBlock labelText = new TextBlock
            {
                Text = label,
                VerticalAlignment = VerticalAlignment.Center,
                FontSize = 11,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#C8CDD4"))
            };
            layout.Children.Add(labelText);

            if (!string.IsNullOrWhiteSpace(suffix))
            {
                TextBlock suffixText = new TextBlock
                {
                    Text = suffix,
                    VerticalAlignment = VerticalAlignment.Center,
                    FontSize = 9.5,
                    Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#8B949E"))
                };
                Grid.SetColumn(suffixText, 1);
                layout.Children.Add(suffixText);
            }

            button.Content = layout;
            button.Click += clickHandler;
            return button;
        }

        private void ProfileProviderOption_Click(object sender, RoutedEventArgs e)
        {
            Button button = sender as Button;
            string provider = button != null ? button.Tag as string : null;
            if (string.IsNullOrWhiteSpace(provider))
            {
                return;
            }

            DirectModelProfile profile = FindAnyProfileForProvider(provider);
            string modelName = profile != null ? profile.ModelName : GetDefaultDirectModel(provider);
            string apiKey = profile != null ? profile.ApiKey ?? string.Empty : string.Empty;
            ApplyProfileEditorSelection(provider, modelName, apiKey, true);
            InvalidateProfileValidation("提供商已变更，请重新测试连接。");
            ProfileProviderPopup.IsOpen = false;
        }

        private void ProfileModelOption_Click(object sender, RoutedEventArgs e)
        {
            Button button = sender as Button;
            string modelName = button != null ? button.Tag as string : null;
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return;
            }

            SetProfileModelSelection(modelName, true);
            InvalidateProfileValidation("模型已变更，请重新测试连接。");
            ProfileModelNamePopup.IsOpen = false;
        }

        private static string GetSelectedComboBoxText(ComboBox comboBox)
        {
            if (comboBox == null)
            {
                return string.Empty;
            }

            ComboBoxItem comboBoxItem = comboBox.SelectedItem as ComboBoxItem;
            if (comboBoxItem != null)
            {
                return Convert.ToString(comboBoxItem.Content) ?? string.Empty;
            }

            string selectedText = Convert.ToString(comboBox.SelectedItem);
            if (!string.IsNullOrWhiteSpace(selectedText))
            {
                return selectedText;
            }

            return comboBox.Text ?? string.Empty;
        }

        private static string GetComboBoxTag(ComboBox comboBox, string fallback)
        {
            string selectedValue = comboBox != null ? comboBox.SelectedValue as string : null;
            if (!string.IsNullOrWhiteSpace(selectedValue))
            {
                return selectedValue;
            }

            ComboBoxItem item = comboBox != null ? comboBox.SelectedItem as ComboBoxItem : null;
            string tag = item != null ? item.Tag as string : null;
            return string.IsNullOrWhiteSpace(tag) ? fallback : tag;
        }

        private static void SelectComboBoxTag(ComboBox comboBox, string tag)
        {
            if (comboBox == null)
            {
                return;
            }

            for (int i = 0; i < comboBox.Items.Count; i++)
            {
                ComboBoxItem item = comboBox.Items[i] as ComboBoxItem;
                if (item != null && string.Equals(item.Tag as string, tag, StringComparison.OrdinalIgnoreCase))
                {
                    comboBox.SelectedIndex = i;
                    return;
                }
            }

            if (comboBox.Items.Count > 0)
            {
                comboBox.SelectedIndex = 0;
            }
        }

        private static string NormalizeConnectionMode(string mode)
        {
            if (string.Equals(mode, ConnectionModeStandard, StringComparison.OrdinalIgnoreCase)
                || string.Equals(mode, LegacyConnectionModeDirect, StringComparison.OrdinalIgnoreCase))
            {
                return ConnectionModeStandard;
            }

            if (string.Equals(mode, ConnectionModeService, StringComparison.OrdinalIgnoreCase))
            {
                return ConnectionModeService;
            }

            return null;
        }

        private static string NormalizeProviderName(string provider)
        {
            if (string.Equals(provider, ProviderCadCopilot, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "AgentBridge", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "official", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "cad-copilot", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "cad_copilot", StringComparison.OrdinalIgnoreCase))
            {
                return ProviderCadCopilot;
            }

            if (string.Equals(provider, ProviderOpenAi, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "gpt", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "gpt-5.5", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "gpt-5.4", StringComparison.OrdinalIgnoreCase))
            {
                return ProviderOpenAi;
            }

            if (string.Equals(provider, ProviderDeepSeek, StringComparison.OrdinalIgnoreCase))
            {
                return ProviderDeepSeek;
            }

            if (string.Equals(provider, ProviderMiniMax, StringComparison.OrdinalIgnoreCase))
            {
                return ProviderMiniMax;
            }

            if (string.Equals(provider, ProviderAnthropic, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "claude", StringComparison.OrdinalIgnoreCase))
            {
                return ProviderAnthropic;
            }

            if (string.Equals(provider, ProviderOpenAiCompatible, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "openai-compatible", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "compatible", StringComparison.OrdinalIgnoreCase))
            {
                return ProviderOpenAiCompatible;
            }

            if (string.Equals(provider, ProviderOllama, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "local", StringComparison.OrdinalIgnoreCase))
            {
                return ProviderOllama;
            }

            if (string.Equals(provider, ProviderEnterprisePrivate, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(provider, "enterprise-private", StringComparison.OrdinalIgnoreCase))
            {
                return ProviderEnterprisePrivate;
            }

            return InferProviderFromModel(provider);
        }

        private static bool IsOfficialProvider(string provider)
        {
            return string.Equals(NormalizeProviderName(provider), ProviderCadCopilot, StringComparison.OrdinalIgnoreCase);
        }

        private static bool ProviderRequiresApiKey(string provider)
        {
            string normalized = NormalizeProviderName(provider);
            return !string.Equals(normalized, ProviderCadCopilot, StringComparison.OrdinalIgnoreCase)
                   && !string.Equals(normalized, ProviderOllama, StringComparison.OrdinalIgnoreCase)
                   && !string.Equals(normalized, ProviderOpenAiCompatible, StringComparison.OrdinalIgnoreCase)
                   && !string.Equals(normalized, ProviderEnterprisePrivate, StringComparison.OrdinalIgnoreCase);
        }
    }
}
