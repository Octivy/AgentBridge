using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using AgentBridge.Engine;
using AgentBridge.LLM;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace AgentBridge.Core
{
    internal static class LocalToolBridge
    {
        private const string ProtocolVersion = "2.0";
        private const string HostProtocolVersion = "1.0";
        private const string HostId = "autocad-main";
        private static readonly object SyncRoot = new object();
        private static JObject _hostManifest;
        private static string _registrationPath;

        private static TcpListener _listener;
        private static CancellationTokenSource _cancellationTokenSource;
        private static Task _serverTask;
        private static string _host = "127.0.0.1";
        private static int _port = 8765;
        private static string _token = string.Empty;
        private static bool _started;

        /// <summary>Whether the bridge is currently listening (starts lazily on first command).</summary>
        public static bool IsRunning
        {
            get
            {
                lock (SyncRoot)
                {
                    return _started;
                }
            }
        }

        public static void Start()
        {
            lock (SyncRoot)
            {
                if (_started)
                {
                    return;
                }

                if (!bool.TryParse(Config.Get("LOCAL_BRIDGE_ENABLED", "true"), out bool enabled) || !enabled)
                {
                    Logger.Info("LocalToolBridge disabled by config.");
                    return;
                }

                _host = Config.Get("LOCAL_BRIDGE_HOST", "127.0.0.1").Trim();
                _token = Config.Get("LOCAL_BRIDGE_TOKEN", string.Empty).Trim();
                if (!int.TryParse(Config.Get("LOCAL_BRIDGE_PORT", "8765"), NumberStyles.Integer, CultureInfo.InvariantCulture, out _port))
                {
                    _port = 8765;
                }

                IPAddress address;
                if (!IPAddress.TryParse(_host, out address))
                {
                    address = IPAddress.Loopback;
                    _host = address.ToString();
                }

                try
                {
                    _cancellationTokenSource = new CancellationTokenSource();
                    _listener = new TcpListener(address, _port);
                    _listener.Start();
                    _serverTask = Task.Run(() => AcceptLoopAsync(_cancellationTokenSource.Token));
                    _started = true;
                    WriteRegistration();
                    Logger.Info("LocalToolBridge listening on http://" + _host + ":" + _port + "/");
                }
                catch (Exception ex)
                {
                    _listener = null;
                    _cancellationTokenSource = null;
                    _serverTask = null;
                    Logger.Error("Failed to start LocalToolBridge: " + ex.Message);
                }
            }
        }

        public static void Stop()
        {
            lock (SyncRoot)
            {
                if (!_started)
                {
                    return;
                }

                try
                {
                    _cancellationTokenSource.Cancel();
                }
                catch
                {
                }

                try
                {
                    _listener.Stop();
                }
                catch
                {
                }

                _listener = null;
                _cancellationTokenSource = null;
                _serverTask = null;
                _started = false;
                RemoveRegistration();
                Logger.Info("LocalToolBridge stopped.");
            }
        }

        private static async Task AcceptLoopAsync(CancellationToken cancellationToken)
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                TcpClient client = null;
                try
                {
                    client = await _listener.AcceptTcpClientAsync().ConfigureAwait(false);
                    _ = Task.Run(() => HandleClientAsync(client, cancellationToken), cancellationToken);
                }
                catch (ObjectDisposedException)
                {
                    break;
                }
                catch (InvalidOperationException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    if (!cancellationToken.IsCancellationRequested)
                    {
                        Logger.Warn("LocalToolBridge accept loop error: " + ex.Message);
                    }

                    if (client != null)
                    {
                        client.Dispose();
                    }
                }
            }
        }

        private static async Task HandleClientAsync(TcpClient client, CancellationToken cancellationToken)
        {
            using (client)
            using (NetworkStream stream = client.GetStream())
            {
                try
                {
                    HttpRequestData request = await ReadRequestAsync(stream, cancellationToken).ConfigureAwait(false);
                    HttpResponseData response = await HandleRequestAsync(request).ConfigureAwait(false);
                    await WriteResponseAsync(stream, response, cancellationToken).ConfigureAwait(false);
                }
                catch (Exception ex)
                {
                    Logger.Warn("LocalToolBridge request failed: " + ex.Message);
                    HttpResponseData response = CreateJsonResponse(HttpStatusCode.InternalServerError, new ToolResponse
                    {
                        RequestId = string.Empty,
                        Ok = false,
                        ErrorCode = "bridge_error",
                        ErrorMessage = ex.Message
                    });

                    try
                    {
                        await WriteResponseAsync(stream, response, cancellationToken).ConfigureAwait(false);
                    }
                    catch
                    {
                    }
                }
            }
        }

        private static async Task<HttpResponseData> HandleRequestAsync(HttpRequestData request)
        {
            if (request == null)
            {
                return CreateTextResponse(HttpStatusCode.BadRequest, "Invalid request.");
            }

            if (!string.IsNullOrWhiteSpace(_token))
            {
                string headerToken;
                request.Headers.TryGetValue("x-cadcopilot-token", out headerToken);
                if (!string.Equals(headerToken, _token, StringComparison.Ordinal))
                {
                    return CreateJsonResponse(HttpStatusCode.Unauthorized, new ToolResponse
                    {
                        Ok = false,
                        ErrorCode = "unauthorized",
                        ErrorMessage = "Missing or invalid local bridge token."
                    });
                }
            }

            if (request.Method == "GET" && request.Path == "/health")
            {
                ToolResponse response = await MainThreadDispatcher.InvokeAsync(BuildHealthResponse).ConfigureAwait(false);
                return CreateJsonResponse(HttpStatusCode.OK, BuildContractHealthResponse(response));
            }

            if (request.Method == "GET" && request.Path == "/manifest")
            {
                JObject manifest = await MainThreadDispatcher.InvokeAsync(BuildManifestResponse).ConfigureAwait(false);
                return CreateJsonResponse(HttpStatusCode.OK, manifest);
            }

            if (request.Method == "POST" && request.Path == "/snapshot")
            {
                LocalToolRequest snapshotPayload = DeserializePayload<LocalToolRequest>(request.Body)
                    ?? new LocalToolRequest { ToolName = "get_drawing_snapshot" };
                try
                {
                    ToolResponse response = await MainThreadDispatcher
                        .InvokeAsync(() => BuildSnapshotResponse(snapshotPayload))
                        .ConfigureAwait(false);
                    JObject result = response.Result as JObject;
                    JToken snapshot = result != null ? result["snapshot"] : null;
                    return CreateJsonResponse(response.Ok ? HttpStatusCode.OK : HttpStatusCode.BadRequest, new JObject
                    {
                        ["ok"] = response.Ok,
                        ["snapshot"] = snapshot ?? (response.Result != null ? JToken.FromObject(response.Result) : JValue.CreateNull()),
                        ["error_code"] = response.ErrorCode,
                        ["error_message"] = response.ErrorMessage
                    });
                }
                catch (Exception ex)
                {
                    return CreateJsonResponse(HttpStatusCode.BadRequest, new JObject
                    {
                        ["ok"] = false,
                        ["error_code"] = "execution_failed",
                        ["error_message"] = ex.Message
                    });
                }
            }

            if (request.Method == "POST" && request.Path == "/rollback")
            {
                LocalToolRequest rollbackBody = DeserializePayload<LocalToolRequest>(request.Body);
                LocalToolRequest rollbackPayload = new LocalToolRequest
                {
                    ToolName = "cad_rollback_transaction",
                    Arguments = new JObject
                    {
                        ["rollback_token"] = rollbackBody != null && rollbackBody.Arguments != null
                            ? rollbackBody.Arguments["rollback_token"]
                            : null
                    },
                    DryRun = false,
                    Caller = "hostmcp"
                };
                ToolResponse response = await ExecuteToolAsync(rollbackPayload).ConfigureAwait(false);
                return CreateJsonResponse(response.Ok ? HttpStatusCode.OK : HttpStatusCode.BadRequest, BuildContractToolResponse(rollbackPayload, response));
            }

            if (request.Method == "POST" && request.Path.StartsWith("/tools/", StringComparison.OrdinalIgnoreCase))
            {
                string hostToolName = Uri.UnescapeDataString(request.Path.Substring("/tools/".Length)).Trim().ToLowerInvariant();
                if (string.IsNullOrWhiteSpace(hostToolName))
                {
                    return CreateJsonResponse(HttpStatusCode.BadRequest, new JObject
                    {
                        ["ok"] = false,
                        ["error_code"] = "invalid_request",
                        ["error_message"] = "tool name is required."
                    });
                }
                LocalToolRequest hostBody = DeserializePayload<LocalToolRequest>(request.Body);
                LocalToolRequest hostPayload = new LocalToolRequest
                {
                    ToolName = hostToolName,
                    Arguments = hostBody != null ? hostBody.Arguments : null,
                    DryRun = hostBody != null ? hostBody.DryRun : (bool?)true,
                    RequestId = hostBody != null ? hostBody.RequestId : null,
                    TraceId = hostBody != null ? hostBody.TraceId : null,
                    Caller = "hostmcp"
                };
                ToolResponse response = await ExecuteToolAsync(hostPayload).ConfigureAwait(false);
                LogToolAudit(hostPayload, response);
                return CreateJsonResponse(response.Ok ? HttpStatusCode.OK : HttpStatusCode.BadRequest, BuildContractToolResponse(hostPayload, response));
            }

            if (request.Method == "POST" && request.Path == "/tools/execute")
            {
                LocalToolRequest payload = DeserializePayload<LocalToolRequest>(request.Body);
                if (payload == null || string.IsNullOrWhiteSpace(payload.ToolName))
                {
                    return CreateJsonResponse(HttpStatusCode.BadRequest, new ToolResponse
                    {
                        Ok = false,
                        ErrorCode = "invalid_request",
                        ErrorMessage = "tool_name is required."
                    });
                }

                ToolResponse response = await ExecuteToolAsync(payload).ConfigureAwait(false);
                LogToolAudit(payload, response);
                return CreateJsonResponse(response.Ok ? HttpStatusCode.OK : HttpStatusCode.BadRequest, response);
            }

            return CreateTextResponse(HttpStatusCode.NotFound, "Not found.");
        }

        private static async Task<ToolResponse> ExecuteToolAsync(LocalToolRequest payload)
        {
            try
            {
                string toolName = (payload.ToolName ?? string.Empty).Trim().ToLowerInvariant();
                if (IsProductWrite(toolName)
                    && !payload.DryRun.GetValueOrDefault()
                    && string.IsNullOrWhiteSpace(ReadString(payload.Arguments, "permission_request_id")))
                {
                    return new ToolResponse
                    {
                        RequestId = payload.RequestId,
                        ToolName = payload.ToolName,
                        Ok = false,
                        ErrorCode = "permission_required",
                        ErrorMessage = "A valid preview permission_request_id is required for CAD writes."
                    };
                }

                switch (toolName)
                {
                    case "cad_health_check":
                        return await MainThreadDispatcher.InvokeAsync(BuildHealthResponse).ConfigureAwait(false);
                    case "get_drawing_snapshot":
                        return await MainThreadDispatcher.InvokeAsync(() => BuildSnapshotResponse(payload)).ConfigureAwait(false);
                    case "list_layers":
                        return await MainThreadDispatcher.InvokeAsync(() => BuildLayerListResponse(payload)).ConfigureAwait(false);
                    case "draw_line":
                        return await MainThreadDispatcher.InvokeAsync(() => ExecuteSingleCommand(payload, BuildLineCommand(payload.Arguments))).ConfigureAwait(false);
                    case "ensure_layer":
                        return await MainThreadDispatcher.InvokeAsync(() => EnsureLayer(payload)).ConfigureAwait(false);
                    case "execute_draw_batch":
                        return await MainThreadDispatcher.InvokeAsync(() => ExecuteBatch(payload)).ConfigureAwait(false);
                    case "arch_draw_outer_outline":
                        return await MainThreadDispatcher.InvokeAsync(() => DrawOuterOutline(payload)).ConfigureAwait(false);
                    case "arch_apply_layer_mapping":
                        return await MainThreadDispatcher.InvokeAsync(() => ApplyLayerMapping(payload)).ConfigureAwait(false);
                    case "cad_rollback_transaction":
                        return await MainThreadDispatcher.InvokeAsync(() => RollbackTransaction(payload)).ConfigureAwait(false);
                    default:
                        return new ToolResponse
                        {
                            RequestId = payload.RequestId,
                            ToolName = payload.ToolName,
                            Ok = false,
                            ErrorCode = "unsupported_tool",
                            ErrorMessage = "Unsupported tool: " + payload.ToolName
                        };
                }
            }
            catch (Exception ex)
            {
                Logger.Warn("LocalToolBridge tool execution failed for " + payload.ToolName + ": " + ex.Message);
                return new ToolResponse
                {
                    RequestId = payload.RequestId,
                    ToolName = payload.ToolName,
                    Ok = false,
                    ErrorCode = "execution_failed",
                    ErrorMessage = ex.Message
                };
            }
        }

        private static bool IsProductWrite(string toolName)
        {
            return toolName == "ensure_layer"
                || toolName == "draw_line"
                || toolName == "execute_draw_batch"
                || toolName == "arch_draw_outer_outline"
                || toolName == "arch_apply_layer_mapping"
                || toolName == "cad_rollback_transaction";
        }

        private static ToolResponse BuildHealthResponse()
        {
            Document document = Application.DocumentManager != null ? Application.DocumentManager.MdiActiveDocument : null;
            object result = new
            {
                bridge = new
                {
                    enabled = _started,
                    host = _host,
                    port = _port,
                    protocol_version = ProtocolVersion,
                    auth_required = !string.IsNullOrWhiteSpace(_token)
                },
                autocad = new
                {
                    document_open = document != null,
                    document_name = document != null ? SafeDocumentName(document) : string.Empty
                },
                plugin = new
                {
                    version = typeof(LocalToolBridge).Assembly.GetName().Version != null
                        ? typeof(LocalToolBridge).Assembly.GetName().Version.ToString()
                        : "unknown"
                }
            };

            return new ToolResponse
            {
                Ok = true,
                ToolName = "cad_health_check",
                Result = result
            };
        }

        private static JObject BuildContractHealthResponse(ToolResponse health)
        {
            JObject result = health.Result as JObject ?? new JObject();
            string pluginVersion = ((result["plugin"] as JObject)?["version"])?.ToString() ?? "unknown";
            JToken documentOpenToken = (result["autocad"] as JObject)?["document_open"];
            bool documentOpen = documentOpenToken != null && documentOpenToken.Type == JTokenType.Boolean && documentOpenToken.Value<bool>();
            return new JObject
            {
                ["ok"] = health.Ok,
                ["tool_name"] = health.ToolName,
                ["result"] = result,
                ["product"] = "AutoCAD",
                ["product_version"] = pluginVersion,
                ["document_open"] = documentOpen,
                ["detail"] = result
            };
        }

        private static JObject BuildManifestResponse()
        {
            JObject manifest = LoadHostManifest();
            manifest["product_version"] = SafeApplicationVersion();
            return manifest;
        }

        private static JObject LoadHostManifest()
        {
            if (_hostManifest != null)
            {
                return _hostManifest;
            }

            JObject manifest = new JObject
            {
                ["schema_version"] = 1,
                ["host_id"] = HostId,
                ["host_kind"] = "autocad",
                ["product"] = "AutoCAD",
                ["product_version"] = SafeApplicationVersion(),
                ["protocol_version"] = HostProtocolVersion,
                ["capabilities"] = new JArray("snapshot", "dry_run", "rollback"),
                ["tools"] = new JArray()
            };
            try
            {
                string manifestPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Resources", "autocad_tools.json");
                if (File.Exists(manifestPath))
                {
                    JObject payload = JObject.Parse(File.ReadAllText(manifestPath));
                    JArray tools = payload["tools"] as JArray;
                    if (tools != null)
                    {
                        manifest["tools"] = tools;
                    }
                }
                else
                {
                    Logger.Warn("Host manifest file missing: " + manifestPath);
                }
            }
            catch (Exception ex)
            {
                Logger.Warn("Failed to load host manifest: " + ex.Message);
            }
            _hostManifest = manifest;
            return manifest;
        }

        private static string SafeApplicationVersion()
        {
            try
            {
                Version version = Application.Version;
                return version != null ? version.ToString() : "unknown";
            }
            catch
            {
                return "unknown";
            }
        }

        private static void WriteRegistration()
        {
            try
            {
                string baseDirectory = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                string directory = Path.Combine(baseDirectory, "AgentBridge", "hosts");
                Directory.CreateDirectory(directory);
                int pid = Process.GetCurrentProcess().Id;
                _registrationPath = Path.Combine(directory, HostId + "-" + pid + ".json");
                JObject registration = new JObject
                {
                    ["schema_version"] = 1,
                    ["host_id"] = HostId,
                    ["host_kind"] = "autocad",
                    ["product"] = "AutoCAD",
                    ["product_version"] = SafeApplicationVersion(),
                    ["protocol_version"] = HostProtocolVersion,
                    ["endpoint"] = "http://" + _host + ":" + _port,
                    ["token"] = _token,
                    ["pid"] = pid,
                    ["registered_at"] = DateTime.UtcNow.ToString("o")
                };
                string temporaryPath = _registrationPath + ".tmp";
                File.WriteAllText(temporaryPath, registration.ToString(Formatting.None));
                if (File.Exists(_registrationPath))
                {
                    File.Delete(_registrationPath);
                }
                File.Move(temporaryPath, _registrationPath);
                Logger.Info("Host registration written: " + _registrationPath);
            }
            catch (Exception ex)
            {
                Logger.Warn("Failed to write host registration: " + ex.Message);
            }
        }

        private static void RemoveRegistration()
        {
            try
            {
                if (!string.IsNullOrWhiteSpace(_registrationPath) && File.Exists(_registrationPath))
                {
                    File.Delete(_registrationPath);
                    Logger.Info("Host registration removed: " + _registrationPath);
                }
            }
            catch (Exception ex)
            {
                Logger.Warn("Failed to remove host registration: " + ex.Message);
            }
            finally
            {
                _registrationPath = null;
            }
        }

        private static JObject BuildContractToolResponse(LocalToolRequest payload, ToolResponse response)
        {
            string rollbackToken = null;
            if (response.Transaction is CadTransactionEnvelope envelope)
            {
                rollbackToken = envelope.RollbackToken;
            }
            return new JObject
            {
                ["ok"] = response.Ok,
                ["tool_name"] = payload.ToolName,
                ["result"] = response.Result != null ? JToken.FromObject(response.Result) : JValue.CreateNull(),
                ["dry_run"] = payload.DryRun.GetValueOrDefault(false),
                ["rollback_token"] = rollbackToken,
                ["error_code"] = response.ErrorCode,
                ["error_message"] = response.ErrorMessage
            };
        }

        private static ToolResponse BuildSnapshotResponse(LocalToolRequest payload)
        {
            SnapshotExtractor extractor = new SnapshotExtractor();
            SnapshotResult snapshot = extractor.ExtractL2Summary();
            return new ToolResponse
            {
                RequestId = payload != null ? payload.RequestId : null,
                ToolName = payload != null ? payload.ToolName : "get_drawing_snapshot",
                Ok = true,
                Result = new
                {
                    layer_count = snapshot.LayerCount,
                    entity_count = snapshot.EntityCount,
                    json_size = snapshot.JsonSize,
                    snapshot = ParseJsonOrText(snapshot.ToJson())
                }
            };
        }

        private static ToolResponse BuildLayerListResponse(LocalToolRequest payload)
        {
            Document document = Application.DocumentManager != null ? Application.DocumentManager.MdiActiveDocument : null;
            if (document == null)
            {
                return new ToolResponse
                {
                    RequestId = payload != null ? payload.RequestId : null,
                    ToolName = payload != null ? payload.ToolName : "list_layers",
                    Ok = false,
                    ErrorCode = "no_document",
                    ErrorMessage = "No active AutoCAD document."
                };
            }

            List<LayerInfo> layers = new List<LayerInfo>();
            using (Transaction transaction = document.Database.TransactionManager.StartOpenCloseTransaction())
            {
                LayerTable layerTable = (LayerTable)transaction.GetObject(document.Database.LayerTableId, OpenMode.ForRead);
                foreach (ObjectId layerId in layerTable)
                {
                    LayerTableRecord layer = transaction.GetObject(layerId, OpenMode.ForRead) as LayerTableRecord;
                    if (layer == null)
                    {
                        continue;
                    }

                    short? colorIndex = null;
                    try
                    {
                        colorIndex = layer.Color != null ? (short?)layer.Color.ColorIndex : null;
                    }
                    catch
                    {
                    }

                    layers.Add(new LayerInfo
                    {
                        Name = layer.Name,
                        Color = colorIndex,
                        IsCurrent = layer.ObjectId == document.Database.Clayer,
                        IsOff = layer.IsOff,
                        IsFrozen = layer.IsFrozen,
                        IsLocked = layer.IsLocked,
                        IsPlottable = layer.IsPlottable,
                        LineType = layer.LinetypeObjectId.IsNull ? string.Empty : layer.LinetypeObjectId.ToString()
                    });
                }

                transaction.Commit();
            }

            return new ToolResponse
            {
                RequestId = payload != null ? payload.RequestId : null,
                ToolName = payload != null ? payload.ToolName : "list_layers",
                Ok = true,
                Result = new
                {
                    document_name = SafeDocumentName(document),
                    layer_count = layers.Count,
                    layers = layers.OrderBy(item => item.Name, StringComparer.OrdinalIgnoreCase).Select(item => new
                    {
                        name = item.Name,
                        semantic_group = GetSemanticLayerGroup(item.Name),
                        color = item.Color,
                        is_current = item.IsCurrent,
                        is_off = item.IsOff,
                        is_frozen = item.IsFrozen,
                        is_locked = item.IsLocked,
                        is_plottable = item.IsPlottable,
                        line_type = item.LineType
                    }).ToArray()
                }
            };
        }

        private static string GetSemanticLayerGroup(string layerName)
        {
            if (string.IsNullOrWhiteSpace(layerName))
            {
                return string.Empty;
            }

            string normalized = layerName.Trim().ToUpperInvariant();
            if (normalized == "WALL" || normalized == "WINDOW" || normalized == "DOTE" || normalized == "STAIR")
            {
                return "plan";
            }

            if (normalized == "PUB_DIM"
                || normalized == "DIM_ELEV"
                || normalized == "DIM_COOR"
                || normalized == "PUB_TEXT"
                || normalized == "SPACE")
            {
                return "annotation";
            }

            if (normalized.StartsWith("S_", StringComparison.OrdinalIgnoreCase))
            {
                return "section";
            }

            if (normalized.StartsWith("E_", StringComparison.OrdinalIgnoreCase))
            {
                return "elevation";
            }

            if (normalized.StartsWith("TMP_", StringComparison.OrdinalIgnoreCase))
            {
                return "temporary";
            }

            return string.Empty;
        }

        private static ToolResponse ExecuteSingleCommand(LocalToolRequest payload, DrawCommand command)
        {
            if (command == null)
            {
                return new ToolResponse
                {
                    RequestId = payload.RequestId,
                    ToolName = payload.ToolName,
                    Ok = false,
                    ErrorCode = "invalid_arguments",
                    ErrorMessage = "Unable to build draw command from arguments."
                };
            }

            return ExecuteCommands(payload, new List<DrawCommand> { command });
        }

        private static ToolResponse ExecuteBatch(LocalToolRequest payload)
        {
            JObject arguments = payload.Arguments ?? new JObject();
            JToken commandsToken = arguments["commands"];
            List<DrawCommand> commands = commandsToken != null
                ? commandsToken.ToObject<List<DrawCommand>>()
                : null;
            if (commands == null || commands.Count == 0)
            {
                return new ToolResponse
                {
                    RequestId = payload.RequestId,
                    ToolName = payload.ToolName,
                    Ok = false,
                    ErrorCode = "invalid_arguments",
                    ErrorMessage = "commands array is required."
                };
            }

            return ExecuteCommands(payload, commands);
        }

        private static ToolResponse ExecuteCommands(LocalToolRequest payload, List<DrawCommand> commands)
        {
            List<string> validationErrors = CommandExecutor.Validate(commands);
            if (validationErrors.Count > 0)
            {
                return new ToolResponse
                {
                    RequestId = payload.RequestId,
                    ToolName = payload.ToolName,
                    Ok = false,
                    ErrorCode = "invalid_arguments",
                    ErrorMessage = string.Join(" ", validationErrors)
                };
            }

            if (payload != null && payload.DryRun.GetValueOrDefault())
            {
                return new ToolResponse
                {
                    RequestId = payload.RequestId,
                    ToolName = payload.ToolName,
                    Ok = true,
                    AffectedEntitiesCount = 0,
                    Result = new
                    {
                        dry_run = true,
                        command_count = commands != null ? commands.Count : 0,
                        commands = commands,
                        caller = payload.Caller,
                        timeout_ms = payload.TimeoutMs
                    },
                    ExecutionLog = new[] { "Dry run only. No CAD entities were created." }
                };
            }

            CadCommandCommitResult commit = CommandExecutor.ExecuteAtomic(commands);
            int count = commit.EntityCount;
            object transactionEnvelope = new CadTransactionEnvelope
            {
                TransactionId = "cadtx_" + Guid.NewGuid().ToString("N"),
                UndoGroup = "CADCOPILOT_MCP",
                RollbackToken = commit.RollbackToken,
                RollbackSupported = commit.RollbackSupported
            };
            List<AffectedEntityInfo> affectedEntities = BuildAffectedEntities(commands, count);
            return new ToolResponse
            {
                RequestId = payload.RequestId,
                ToolName = payload.ToolName,
                Ok = true,
                AffectedEntitiesCount = count,
                AffectedEntities = affectedEntities,
                Transaction = transactionEnvelope,
                Result = new
                {
                    dry_run = false,
                    affected_entities_count = count,
                    affected_entities = affectedEntities,
                    transaction = transactionEnvelope,
                    entity_handles = commit.EntityHandles,
                    verified = commit.Verified,
                    commands = commands,
                    caller = payload.Caller,
                    timeout_ms = payload.TimeoutMs
                },
                ExecutionLog = new[] { "Executed " + count + " CAD entities." }
            };
        }

        private static ToolResponse DrawOuterOutline(LocalToolRequest payload)
        {
            JObject arguments = payload.Arguments ?? new JObject();
            JToken boundaryToken = arguments["boundary"] ?? arguments.SelectToken("outline.boundary");
            double[][] boundary = boundaryToken != null ? boundaryToken.ToObject<double[][]>() : null;
            DrawCommand command = new DrawCommand
            {
                Type = "POLYLINE",
                Layer = ReadString(arguments, "layer") ?? "AI-OUTLINE",
                Points = boundary,
                Closed = true
            };
            return ExecuteSingleCommand(payload, command);
        }

        private static ToolResponse ApplyLayerMapping(LocalToolRequest payload)
        {
            JObject arguments = payload.Arguments ?? new JObject();
            JArray mappings = arguments["mappings"] as JArray;
            if (mappings == null || mappings.Count == 0)
            {
                return InvalidArguments(payload, "mappings array is required.");
            }
            if (payload.DryRun.GetValueOrDefault())
            {
                return new ToolResponse
                {
                    RequestId = payload.RequestId,
                    ToolName = payload.ToolName,
                    Ok = true,
                    AffectedEntitiesCount = 0,
                    Result = new { dry_run = true, mappings = mappings, verified = false }
                };
            }

            Document document = Application.DocumentManager.MdiActiveDocument;
            if (document == null)
            {
                return InvalidArguments(payload, "No active AutoCAD document.");
            }
            Dictionary<string, string> targets = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (JObject mapping in mappings.OfType<JObject>())
            {
                string source = ReadString(mapping, "source_layer");
                string target = ReadString(mapping, "target_layer");
                if (string.IsNullOrWhiteSpace(source) || string.IsNullOrWhiteSpace(target))
                {
                    return InvalidArguments(payload, "Each mapping requires source_layer and target_layer.");
                }
                targets[source] = target;
            }

            HashSet<string> requestedHandles = new HashSet<string>(
                (arguments["entity_handles"] as JArray ?? new JArray()).Values<string>(),
                StringComparer.OrdinalIgnoreCase);
            Dictionary<string, string> originalLayers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            using (DocumentLock documentLock = document.LockDocument())
            using (Transaction transaction = document.Database.TransactionManager.StartTransaction())
            {
                foreach (string target in targets.Values.Distinct(StringComparer.OrdinalIgnoreCase))
                {
                    DrawingTools.EnsureLayer(transaction, document.Database, target, null);
                }
                BlockTableRecord currentSpace = (BlockTableRecord)transaction.GetObject(document.Database.CurrentSpaceId, OpenMode.ForRead);
                foreach (ObjectId id in currentSpace)
                {
                    Entity entity = transaction.GetObject(id, OpenMode.ForRead) as Entity;
                    if (entity == null || entity.IsErased || !targets.ContainsKey(entity.Layer))
                    {
                        continue;
                    }
                    string handle = entity.Handle.ToString();
                    if (requestedHandles.Count > 0 && !requestedHandles.Contains(handle))
                    {
                        continue;
                    }
                    originalLayers[handle] = entity.Layer;
                    entity.UpgradeOpen();
                    entity.Layer = targets[entity.Layer];
                }
                transaction.Commit();
            }

            Action<Database, Transaction> restore = (database, transaction) =>
            {
                foreach (KeyValuePair<string, string> item in originalLayers)
                {
                    long value;
                    if (!long.TryParse(item.Key, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out value)) continue;
                    ObjectId id = database.GetObjectId(false, new Handle(value), 0);
                    Entity entity = id.IsNull ? null : transaction.GetObject(id, OpenMode.ForWrite, false) as Entity;
                    if (entity != null && !entity.IsErased) entity.Layer = item.Value;
                }
            };
            string rollbackToken = CommandExecutor.RegisterMutationRollback(document.Database, originalLayers.Keys, restore);
            object transactionEnvelope = new CadTransactionEnvelope
            {
                TransactionId = "cadtx_" + Guid.NewGuid().ToString("N"),
                UndoGroup = "CADCOPILOT_LAYER_MAPPING",
                RollbackToken = rollbackToken,
                RollbackSupported = !string.IsNullOrWhiteSpace(rollbackToken)
            };
            return new ToolResponse
            {
                RequestId = payload.RequestId,
                ToolName = payload.ToolName,
                Ok = true,
                AffectedEntitiesCount = originalLayers.Count,
                Transaction = transactionEnvelope,
                Result = new
                {
                    dry_run = false,
                    affected_entities_count = originalLayers.Count,
                    entity_handles = originalLayers.Keys.ToArray(),
                    verified = true,
                    transaction = transactionEnvelope
                }
            };
        }

        private static ToolResponse RollbackTransaction(LocalToolRequest payload)
        {
            string token = ReadString(payload.Arguments, "rollback_token");
            if (string.IsNullOrWhiteSpace(token))
            {
                return InvalidArguments(payload, "rollback_token is required.");
            }
            Document document = Application.DocumentManager.MdiActiveDocument;
            if (document == null)
            {
                return InvalidArguments(payload, "No active AutoCAD document.");
            }
            if (payload.DryRun.GetValueOrDefault())
            {
                CadCommandRollbackDescription description = CommandExecutor.DescribeRollback(token);
                return new ToolResponse
                {
                    RequestId = payload.RequestId,
                    ToolName = payload.ToolName,
                    Ok = true,
                    AffectedEntitiesCount = 0,
                    Result = new { dry_run = true, entity_handles = description.EntityHandles, verified = false }
                };
            }
            CadCommandCommitResult result = CommandExecutor.RollbackAtomic(document, token);
            return new ToolResponse
            {
                RequestId = payload.RequestId,
                ToolName = payload.ToolName,
                Ok = result.Verified,
                AffectedEntitiesCount = result.EntityCount,
                Result = new { dry_run = false, entity_handles = result.EntityHandles, verified = result.Verified }
            };
        }

        private static ToolResponse InvalidArguments(LocalToolRequest payload, string message)
        {
            return new ToolResponse
            {
                RequestId = payload != null ? payload.RequestId : null,
                ToolName = payload != null ? payload.ToolName : null,
                Ok = false,
                ErrorCode = "invalid_arguments",
                ErrorMessage = message
            };
        }

        private static ToolResponse EnsureLayer(LocalToolRequest payload)
        {
            JObject arguments = payload.Arguments ?? new JObject();
            string layerName = ReadString(arguments, "layer") ?? ReadString(arguments, "layer_name");
            int? color = ReadNullableInt(arguments, "color");
            if (string.IsNullOrWhiteSpace(layerName))
            {
                return new ToolResponse
                {
                    RequestId = payload.RequestId,
                    ToolName = payload.ToolName,
                    Ok = false,
                    ErrorCode = "invalid_arguments",
                    ErrorMessage = "layer is required."
                };
            }

            if (payload.DryRun.GetValueOrDefault())
            {
                return new ToolResponse
                {
                    RequestId = payload.RequestId,
                    ToolName = payload.ToolName,
                    Ok = true,
                    Result = new
                    {
                        dry_run = true,
                        layer = layerName,
                        color = color,
                        caller = payload.Caller,
                        timeout_ms = payload.TimeoutMs
                    },
                    ExecutionLog = new[] { "Dry run only. Layer creation was not executed." }
                };
            }

            Document document = Application.DocumentManager != null ? Application.DocumentManager.MdiActiveDocument : null;
            if (document == null)
            {
                return new ToolResponse
                {
                    RequestId = payload.RequestId,
                    ToolName = payload.ToolName,
                    Ok = false,
                    ErrorCode = "no_document",
                    ErrorMessage = "No active AutoCAD document."
                };
            }

            using (DocumentLock documentLock = document.LockDocument())
            using (Transaction transaction = document.Database.TransactionManager.StartTransaction())
            {
                DrawingTools.EnsureLayer(transaction, document.Database, layerName, color);
                transaction.Commit();
            }

            object transactionEnvelope = BuildTransactionEnvelope(payload);
            return new ToolResponse
            {
                RequestId = payload.RequestId,
                ToolName = payload.ToolName,
                Ok = true,
                AffectedEntitiesCount = 0,
                AffectedEntities = new List<AffectedEntityInfo>(),
                Transaction = transactionEnvelope,
                Result = new
                {
                    dry_run = payload.DryRun.GetValueOrDefault(),
                    layer = layerName,
                    color = color,
                    affected_entities_count = 0,
                    affected_entities = new List<AffectedEntityInfo>(),
                    transaction = transactionEnvelope,
                    caller = payload.Caller,
                    timeout_ms = payload.TimeoutMs
                },
                ExecutionLog = payload.DryRun.GetValueOrDefault()
                    ? new[] { "Layer validation only. No drawing entities were created." }
                : new[] { "Layer ensured successfully." }
            };
        }

        private static CadTransactionEnvelope BuildTransactionEnvelope(LocalToolRequest payload)
        {
            string taskId = payload != null && payload.Arguments != null ? ReadString(payload.Arguments, "task_id") : string.Empty;
            string transactionId = "cadtx_" + Guid.NewGuid().ToString("N");
            string undoGroup = !string.IsNullOrWhiteSpace(taskId)
                ? "CADCOPILOT_TASK_" + taskId.Trim()
                : "CADCOPILOT_" + transactionId;

            return new CadTransactionEnvelope
            {
                TransactionId = transactionId,
                UndoGroup = undoGroup,
                RollbackToken = transactionId,
                RollbackSupported = true
            };
        }

        private static List<AffectedEntityInfo> BuildAffectedEntities(List<DrawCommand> commands, int count)
        {
            List<AffectedEntityInfo> affected = new List<AffectedEntityInfo>();
            if (commands == null || count <= 0)
            {
                return affected;
            }

            int limit = Math.Min(commands.Count, count);
            for (int index = 0; index < limit; index++)
            {
                DrawCommand command = commands[index];
                affected.Add(new AffectedEntityInfo
                {
                    EntityId = string.Empty,
                    Operation = "created",
                    EntityType = command != null ? command.Type ?? string.Empty : string.Empty,
                    Layer = command != null ? command.Layer ?? string.Empty : string.Empty
                });
            }

            return affected;
        }

        private static void LogToolAudit(LocalToolRequest payload, ToolResponse response)
        {
            if (payload == null)
            {
                return;
            }

            bool confirmedByLocalUser = ReadBool(payload.Arguments, "confirmed_by_local_user").GetValueOrDefault();
            string taskId = ReadString(payload.Arguments, "task_id") ?? string.Empty;
            string traceId = payload.TraceId ?? string.Empty;
            string requestId = payload.RequestId ?? string.Empty;
            string toolName = payload.ToolName ?? string.Empty;
            string caller = payload.Caller ?? string.Empty;
            bool dryRun = payload.DryRun.GetValueOrDefault();
            bool ok = response != null && response.Ok;
            int affected = response != null && response.AffectedEntitiesCount.HasValue ? response.AffectedEntitiesCount.Value : 0;

            Logger.Info(
                "LocalToolBridge audit"
                + " tool=" + toolName
                + " request_id=" + requestId
                + " trace_id=" + traceId
                + " task_id=" + taskId
                + " caller=" + caller
                + " dry_run=" + dryRun.ToString()
                + " confirmed_by_local_user=" + confirmedByLocalUser.ToString()
                + " ok=" + ok.ToString()
                + " affected_entities_count=" + affected.ToString(CultureInfo.InvariantCulture));
        }

        private static DrawCommand BuildLineCommand(JObject arguments)
        {
            return new DrawCommand
            {
                Type = "LINE",
                Layer = ReadString(arguments, "layer"),
                Color = ReadNullableInt(arguments, "color"),
                Start = ReadPoint(arguments, "start"),
                End = ReadPoint(arguments, "end")
            };
        }

        private static string SafeDocumentName(Document document)
        {
            try
            {
                return !string.IsNullOrWhiteSpace(document.Name) ? Path.GetFileName(document.Name) : "未命名图纸";
            }
            catch
            {
                return "未命名图纸";
            }
        }

        private static object ParseJsonOrText(string json)
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                return new JObject();
            }

            try
            {
                return JToken.Parse(json);
            }
            catch
            {
                return json;
            }
        }

        private static T DeserializePayload<T>(string json) where T : class
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                return null;
            }

            return JsonConvert.DeserializeObject<T>(json);
        }

        private static string ReadString(JObject arguments, string key)
        {
            if (arguments == null || string.IsNullOrWhiteSpace(key))
            {
                return null;
            }

            JToken token = arguments[key];
            return token != null && token.Type != JTokenType.Null ? token.ToString() : null;
        }

        private static int? ReadNullableInt(JObject arguments, string key)
        {
            JToken token = arguments != null ? arguments[key] : null;
            return token != null && token.Type != JTokenType.Null ? token.Value<int?>() : null;
        }

        private static bool? ReadBool(JObject arguments, string key)
        {
            JToken token = arguments != null ? arguments[key] : null;
            return token != null && token.Type != JTokenType.Null ? token.Value<bool?>() : null;
        }

        private static double? ReadNullableDouble(JObject arguments, string key)
        {
            JToken token = arguments != null ? arguments[key] : null;
            return token != null && token.Type != JTokenType.Null ? token.Value<double?>() : null;
        }

        private static double[] ReadPoint(JObject arguments, string key)
        {
            JToken token = arguments != null ? arguments[key] : null;
            if (token == null || token.Type == JTokenType.Null)
            {
                return null;
            }

            return token.ToObject<double[]>();
        }

        private static async Task<HttpRequestData> ReadRequestAsync(NetworkStream stream, CancellationToken cancellationToken)
        {
            List<byte> bytes = new List<byte>();
            byte[] buffer = new byte[4096];
            int headerEnd = -1;

            while (headerEnd < 0)
            {
                int read = await stream.ReadAsync(buffer, 0, buffer.Length, cancellationToken).ConfigureAwait(false);
                if (read <= 0)
                {
                    break;
                }

                bytes.AddRange(buffer.Take(read));
                headerEnd = FindHeaderEnd(bytes);
                if (bytes.Count > 65536)
                {
                    throw new InvalidOperationException("Request headers too large.");
                }
            }

            if (headerEnd < 0)
            {
                throw new InvalidOperationException("Incomplete HTTP request.");
            }

            byte[] allBytes = bytes.ToArray();
            string headerText = Encoding.UTF8.GetString(allBytes, 0, headerEnd);
            string[] headerLines = headerText.Split(new[] { "\r\n" }, StringSplitOptions.None);
            if (headerLines.Length == 0)
            {
                throw new InvalidOperationException("Invalid HTTP request.");
            }

            string[] requestLineParts = headerLines[0].Split(' ');
            if (requestLineParts.Length < 2)
            {
                throw new InvalidOperationException("Invalid request line.");
            }

            Dictionary<string, string> headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            for (int index = 1; index < headerLines.Length; index++)
            {
                string line = headerLines[index];
                int separator = line.IndexOf(':');
                if (separator <= 0)
                {
                    continue;
                }

                string name = line.Substring(0, separator).Trim();
                string value = line.Substring(separator + 1).Trim();
                headers[name] = value;
            }

            int contentLength = 0;
            if (headers.TryGetValue("Content-Length", out string contentLengthValue))
            {
                int.TryParse(contentLengthValue, NumberStyles.Integer, CultureInfo.InvariantCulture, out contentLength);
            }

            int bodyOffset = headerEnd + 4;
            int alreadyBuffered = allBytes.Length - bodyOffset;
            byte[] bodyBytes = new byte[contentLength > 0 ? contentLength : 0];
            if (contentLength > 0)
            {
                if (alreadyBuffered > 0)
                {
                    Buffer.BlockCopy(allBytes, bodyOffset, bodyBytes, 0, Math.Min(alreadyBuffered, contentLength));
                }

                int copied = Math.Min(alreadyBuffered, contentLength);
                while (copied < contentLength)
                {
                    int read = await stream.ReadAsync(bodyBytes, copied, contentLength - copied, cancellationToken).ConfigureAwait(false);
                    if (read <= 0)
                    {
                        break;
                    }

                    copied += read;
                }
            }

            Uri uri = new Uri("http://localhost" + requestLineParts[1]);
            return new HttpRequestData
            {
                Method = requestLineParts[0].Trim().ToUpperInvariant(),
                Path = uri.AbsolutePath,
                Headers = headers,
                Body = contentLength > 0 ? Encoding.UTF8.GetString(bodyBytes) : string.Empty
            };
        }

        private static int FindHeaderEnd(List<byte> bytes)
        {
            for (int index = 0; index <= bytes.Count - 4; index++)
            {
                if (bytes[index] == 13 && bytes[index + 1] == 10 && bytes[index + 2] == 13 && bytes[index + 3] == 10)
                {
                    return index;
                }
            }

            return -1;
        }

        private static async Task WriteResponseAsync(NetworkStream stream, HttpResponseData response, CancellationToken cancellationToken)
        {
            byte[] body = Encoding.UTF8.GetBytes(response.Body ?? string.Empty);
            StringBuilder headerBuilder = new StringBuilder();
            headerBuilder.Append("HTTP/1.1 ");
            headerBuilder.Append((int)response.StatusCode);
            headerBuilder.Append(' ');
            headerBuilder.Append(response.StatusCode);
            headerBuilder.Append("\r\n");
            headerBuilder.Append("Content-Type: ");
            headerBuilder.Append(response.ContentType ?? "application/json; charset=utf-8");
            headerBuilder.Append("\r\n");
            headerBuilder.Append("Content-Length: ");
            headerBuilder.Append(body.Length.ToString(CultureInfo.InvariantCulture));
            headerBuilder.Append("\r\n");
            headerBuilder.Append("Connection: close\r\n");
            headerBuilder.Append("Access-Control-Allow-Origin: *\r\n\r\n");

            byte[] headerBytes = Encoding.UTF8.GetBytes(headerBuilder.ToString());
            await stream.WriteAsync(headerBytes, 0, headerBytes.Length, cancellationToken).ConfigureAwait(false);
            await stream.WriteAsync(body, 0, body.Length, cancellationToken).ConfigureAwait(false);
            await stream.FlushAsync(cancellationToken).ConfigureAwait(false);
        }

        private static HttpResponseData CreateJsonResponse(HttpStatusCode statusCode, object payload)
        {
            return new HttpResponseData
            {
                StatusCode = statusCode,
                ContentType = "application/json; charset=utf-8",
                Body = JsonConvert.SerializeObject(payload, Formatting.None)
            };
        }

        private static HttpResponseData CreateTextResponse(HttpStatusCode statusCode, string body)
        {
            return new HttpResponseData
            {
                StatusCode = statusCode,
                ContentType = "text/plain; charset=utf-8",
                Body = body ?? string.Empty
            };
        }

        private sealed class HttpRequestData
        {
            public string Method { get; set; }

            public string Path { get; set; }

            public Dictionary<string, string> Headers { get; set; }

            public string Body { get; set; }
        }

        private sealed class HttpResponseData
        {
            public HttpStatusCode StatusCode { get; set; }

            public string ContentType { get; set; }

            public string Body { get; set; }
        }

        private sealed class LayerInfo
        {
            public string Name { get; set; }

            public short? Color { get; set; }

            public bool IsCurrent { get; set; }

            public bool IsOff { get; set; }

            public bool IsFrozen { get; set; }

            public bool IsLocked { get; set; }

            public bool IsPlottable { get; set; }

            public string LineType { get; set; }
        }

        private sealed class LocalToolRequest
        {
            [JsonProperty("request_id")]
            public string RequestId { get; set; }

            [JsonProperty("trace_id")]
            public string TraceId { get; set; }

            [JsonProperty("tool_name")]
            public string ToolName { get; set; }

            [JsonProperty("arguments")]
            public JObject Arguments { get; set; }

            [JsonProperty("document_hint")]
            public string DocumentHint { get; set; }

            [JsonProperty("timeout_ms")]
            public int? TimeoutMs { get; set; }

            [JsonProperty("caller")]
            public string Caller { get; set; }

            [JsonProperty("dry_run")]
            public bool? DryRun { get; set; }
        }

        private sealed class ToolResponse
        {
            [JsonProperty("request_id")]
            public string RequestId { get; set; }

            [JsonProperty("tool_name")]
            public string ToolName { get; set; }

            [JsonProperty("ok")]
            public bool Ok { get; set; }

            [JsonProperty("result")]
            public object Result { get; set; }

            [JsonProperty("error_code")]
            public string ErrorCode { get; set; }

            [JsonProperty("error_message")]
            public string ErrorMessage { get; set; }

            [JsonProperty("execution_log")]
            public IEnumerable<string> ExecutionLog { get; set; }

            [JsonProperty("affected_entities_count")]
            public int? AffectedEntitiesCount { get; set; }

            [JsonProperty("affected_entities")]
            public IEnumerable<AffectedEntityInfo> AffectedEntities { get; set; }

            [JsonProperty("transaction")]
            public object Transaction { get; set; }
        }

        private sealed class AffectedEntityInfo
        {
            [JsonProperty("entity_id")]
            public string EntityId { get; set; }

            [JsonProperty("operation")]
            public string Operation { get; set; }

            [JsonProperty("type")]
            public string EntityType { get; set; }

            [JsonProperty("layer")]
            public string Layer { get; set; }
        }

        private sealed class CadTransactionEnvelope
        {
            [JsonProperty("transaction_id")]
            public string TransactionId { get; set; }

            [JsonProperty("undo_group")]
            public string UndoGroup { get; set; }

            [JsonProperty("rollback_token")]
            public string RollbackToken { get; set; }

            [JsonProperty("rollback_supported")]
            public bool RollbackSupported { get; set; }
        }
    }
}
