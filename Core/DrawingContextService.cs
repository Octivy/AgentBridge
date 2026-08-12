using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using AgentBridge.Engine;
using Newtonsoft.Json;

namespace AgentBridge.Core
{
    public static class DrawingContextService
    {
        private static readonly object SyncObject = new object();

        private static Document _document;
        private static bool _initialized;
        private static bool _snapshotDirty = true;
        private static SnapshotResult _cachedSnapshot = new SnapshotResult();
        private static DateTime _lastSnapshotUtc = DateTime.MinValue;
        private static DateTime _lastChangeUtc = DateTime.MinValue;
        private static string _lastCommandName = "无";
        private static string _lastCommandState = "idle";
        private static int _appendedSinceRefresh;
        private static int _modifiedSinceRefresh;
        private static int _erasedSinceRefresh;

        public static void Initialize()
        {
            if (_initialized)
            {
                return;
            }

            Application.DocumentManager.DocumentActivated += OnDocumentActivated;
            AttachToDocument(Application.DocumentManager.MdiActiveDocument);
            _initialized = true;
            Logger.Info("DrawingContextService initialized.");
        }

        public static void Shutdown()
        {
            if (!_initialized)
            {
                return;
            }

            Application.DocumentManager.DocumentActivated -= OnDocumentActivated;
            AttachToDocument(null);
            _initialized = false;
        }

        public static string BuildAugmentedPrompt(string userText)
        {
            EnsureActiveDocumentAttached();

            Document document = _document;
            if (document == null)
            {
                return string.IsNullOrWhiteSpace(userText)
                    ? "请根据用户提供的信息协助完成 CAD 对话。"
                    : userText;
            }

            SnapshotResult snapshot = GetSnapshot(document);
            string snapshotJson = Limit(snapshot != null ? snapshot.ToJson() : "{}", 6000);
            string selectionJson = BuildSelectionSummary(document);
            string documentName = SafeGetDocumentName(document);

            string contextBlock =
                "[CAD_CONTEXT]\n" +
                "当前图纸: " + documentName + "\n" +
                "最近命令: " + _lastCommandName + " (" + _lastCommandState + ")\n" +
                "最近变更: 新增 " + _appendedSinceRefresh + "，修改 " + _modifiedSinceRefresh + "，删除 " + _erasedSinceRefresh + "\n" +
                "最近变更时间: " + FormatTime(_lastChangeUtc) + "\n" +
                "上下文刷新时间: " + FormatTime(_lastSnapshotUtc) + "\n" +
                "当前选择摘要: " + selectionJson + "\n" +
                "当前图纸 L2 摘要: " + snapshotJson + "\n" +
                "[/CAD_CONTEXT]\n\n" +
                "请优先依据 CAD_CONTEXT 中的图纸状态、选择对象和最近变更进行回答或绘图；如果上下文不足，请明确指出缺少的尺寸、约束或目标对象。selection_summary 中的 semantic_hints 是几何或块名推断出的候选标签，不是绝对事实。";

            string normalizedUserText = string.IsNullOrWhiteSpace(userText)
                ? "请根据当前 CAD 上下文协助用户。"
                : userText.Trim();

            return contextBlock + "\n\n用户请求:\n" + normalizedUserText;
        }

        public static DrawingContextSummary GetUiSummary()
        {
            EnsureActiveDocumentAttached();

            Document document = _document;
            if (document == null)
            {
                return new DrawingContextSummary
                {
                    DocumentName = "未连接图纸",
                    LastCommandName = _lastCommandName,
                    LastCommandState = _lastCommandState,
                    LastChangeText = FormatTime(_lastChangeUtc),
                    SnapshotRefreshText = FormatTime(_lastSnapshotUtc),
                    SelectionSummaryJson = "{\"count\":0,\"entities\":[]}",
                    SnapshotPreviewJson = "{}"
                };
            }

            SnapshotResult snapshot = GetSnapshot(document);
            return new DrawingContextSummary
            {
                DocumentName = SafeGetDocumentName(document),
                LastCommandName = _lastCommandName,
                LastCommandState = _lastCommandState,
                LastChangeText = FormatTime(_lastChangeUtc),
                SnapshotRefreshText = FormatTime(_lastSnapshotUtc),
                AppendedSinceRefresh = _appendedSinceRefresh,
                ModifiedSinceRefresh = _modifiedSinceRefresh,
                ErasedSinceRefresh = _erasedSinceRefresh,
                LayerCount = snapshot != null ? snapshot.LayerCount : 0,
                EntityCount = snapshot != null ? snapshot.EntityCount : 0,
                JsonSize = snapshot != null ? snapshot.JsonSize : 0,
                SelectionSummaryJson = BuildSelectionSummary(document),
                SnapshotPreviewJson = Limit(snapshot != null ? snapshot.ToJson() : "{}", 1200)
            };
        }

        private static void EnsureActiveDocumentAttached()
        {
            Document activeDocument = Application.DocumentManager != null
                ? Application.DocumentManager.MdiActiveDocument
                : null;

            if (!ReferenceEquals(activeDocument, _document))
            {
                AttachToDocument(activeDocument);
            }
        }

        private static void AttachToDocument(Document document)
        {
            lock (SyncObject)
            {
                if (ReferenceEquals(_document, document))
                {
                    return;
                }

                if (_document != null)
                {
                    _document.CommandWillStart -= OnCommandWillStart;
                    _document.CommandEnded -= OnCommandEnded;
                    _document.CommandCancelled -= OnCommandCancelled;
                    _document.CommandFailed -= OnCommandFailed;

                    if (_document.Database != null)
                    {
                        _document.Database.ObjectAppended -= OnObjectAppended;
                        _document.Database.ObjectModified -= OnObjectModified;
                        _document.Database.ObjectErased -= OnObjectErased;
                    }
                }

                _document = document;
                _snapshotDirty = true;
                _cachedSnapshot = new SnapshotResult();
                _appendedSinceRefresh = 0;
                _modifiedSinceRefresh = 0;
                _erasedSinceRefresh = 0;

                if (_document == null)
                {
                    return;
                }

                _document.CommandWillStart += OnCommandWillStart;
                _document.CommandEnded += OnCommandEnded;
                _document.CommandCancelled += OnCommandCancelled;
                _document.CommandFailed += OnCommandFailed;
                _document.Database.ObjectAppended += OnObjectAppended;
                _document.Database.ObjectModified += OnObjectModified;
                _document.Database.ObjectErased += OnObjectErased;
                _lastCommandName = "文档切换";
                _lastCommandState = "activated";
                _lastChangeUtc = DateTime.UtcNow;
            }
        }

        private static SnapshotResult GetSnapshot(Document document)
        {
            lock (SyncObject)
            {
                if (!_snapshotDirty && _cachedSnapshot != null)
                {
                    return _cachedSnapshot;
                }

                SnapshotExtractor extractor = new SnapshotExtractor();
                _cachedSnapshot = extractor.ExtractL2Summary();
                _snapshotDirty = false;
                _lastSnapshotUtc = DateTime.UtcNow;
                return _cachedSnapshot;
            }
        }

        private static string BuildSelectionSummary(Document document)
        {
            try
            {
                PromptSelectionResult result = document.Editor.SelectImplied();
                if (result.Status != PromptStatus.OK || result.Value == null || result.Value.Count == 0)
                {
                    return "{\"count\":0,\"entities\":[]}";
                }

                List<Dictionary<string, object>> entities = new List<Dictionary<string, object>>();
                using (Transaction transaction = document.Database.TransactionManager.StartOpenCloseTransaction())
                {
                    foreach (SelectedObject selectedObject in result.Value)
                    {
                        if (selectedObject == null || selectedObject.ObjectId.IsNull)
                        {
                            continue;
                        }

                        Entity entity = transaction.GetObject(selectedObject.ObjectId, OpenMode.ForRead) as Entity;
                        if (entity == null)
                        {
                            continue;
                        }

                        entities.Add(CreateEntitySummary(transaction, entity));
                        if (entities.Count >= 10)
                        {
                            break;
                        }
                    }

                    transaction.Commit();
                }

                List<string> semanticHints = entities
                    .SelectMany(GetSemanticHints)
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .OrderBy(item => item)
                    .ToList();

                List<string> layers = entities
                    .Select(GetLayerName)
                    .Where(item => !string.IsNullOrWhiteSpace(item))
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .OrderBy(item => item)
                    .ToList();

                return JsonConvert.SerializeObject(new
                {
                    count = result.Value.Count,
                    layers = layers,
                    semantic_hints = semanticHints,
                    entities = entities
                }, Formatting.None);
            }
            catch (Exception ex)
            {
                Logger.Warn("Failed to inspect current selection: " + ex.Message);
                return "{\"count\":0,\"entities\":[],\"warning\":\"selection_unavailable\"}";
            }
        }

        private static Dictionary<string, object> CreateEntitySummary(Transaction transaction, Entity entity)
        {
            Dictionary<string, object> payload = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase)
            {
                ["type"] = entity.GetType().Name,
                ["layer"] = string.IsNullOrWhiteSpace(entity.Layer) ? "0" : entity.Layer
            };

            List<string> semanticHints = new List<string>();

            try
            {
                Extents3d extents = entity.GeometricExtents;
                double width = Math.Abs(extents.MaxPoint.X - extents.MinPoint.X);
                double height = Math.Abs(extents.MaxPoint.Y - extents.MinPoint.Y);
                payload["bounds"] = new
                {
                    min = new[] { Round(extents.MinPoint.X), Round(extents.MinPoint.Y) },
                    max = new[] { Round(extents.MaxPoint.X), Round(extents.MaxPoint.Y) }
                };
                payload["width"] = Round(width);
                payload["height"] = Round(height);
                payload["dominant_axis"] = width >= height ? "x" : "y";
            }
            catch
            {
            }

            DBText dbText = entity as DBText;
            if (dbText != null)
            {
                payload["text"] = dbText.TextString;
                payload["position"] = new[] { Round(dbText.Position.X), Round(dbText.Position.Y) };
                semanticHints.Add("text_annotation_candidate");
                payload["semantic_hints"] = semanticHints;
                return payload;
            }

            MText mText = entity as MText;
            if (mText != null)
            {
                payload["text"] = mText.Text;
                payload["position"] = new[] { Round(mText.Location.X), Round(mText.Location.Y) };
                semanticHints.Add("text_annotation_candidate");
                payload["semantic_hints"] = semanticHints;
                return payload;
            }

            Line line = entity as Line;
            if (line != null)
            {
                payload["start"] = new[] { Round(line.StartPoint.X), Round(line.StartPoint.Y) };
                payload["end"] = new[] { Round(line.EndPoint.X), Round(line.EndPoint.Y) };
                payload["length"] = Round(line.Length);
                if (line.Length >= 2000)
                {
                    semanticHints.Add("wall_segment_candidate");
                }

                payload["semantic_hints"] = semanticHints;
                return payload;
            }

            Circle circle = entity as Circle;
            if (circle != null)
            {
                payload["center"] = new[] { Round(circle.Center.X), Round(circle.Center.Y) };
                payload["radius"] = Round(circle.Radius);
                payload["diameter"] = Round(circle.Radius * 2);
                payload["area"] = Round(Math.PI * circle.Radius * circle.Radius);
                semanticHints.Add("circular_feature_candidate");
                payload["semantic_hints"] = semanticHints;
                return payload;
            }

            Arc arc = entity as Arc;
            if (arc != null)
            {
                payload["center"] = new[] { Round(arc.Center.X), Round(arc.Center.Y) };
                payload["radius"] = Round(arc.Radius);
                payload["length"] = Round(arc.Length);
                semanticHints.Add("arc_feature_candidate");
                payload["semantic_hints"] = semanticHints;
                return payload;
            }

            Polyline polyline = entity as Polyline;
            if (polyline != null)
            {
                payload["vertices"] = polyline.NumberOfVertices;
                payload["closed"] = polyline.Closed;
                payload["length"] = Round(polyline.Length);
                payload["vertex_preview"] = GetPolylinePreview(polyline);

                if (polyline.Closed)
                {
                    payload["area"] = Round(Math.Abs(polyline.Area));
                }

                if (IsRectangleCandidate(polyline))
                {
                    semanticHints.Add("rectangle_candidate");

                    double width = GetNumericMetric(payload, "width");
                    double height = GetNumericMetric(payload, "height");
                    double area = GetNumericMetric(payload, "area");
                    double longSide = Math.Max(width, height);
                    double shortSide = Math.Min(width, height);

                    if (polyline.Closed && width >= 2000 && height >= 2000 && area >= 4000000)
                    {
                        semanticHints.Add("room_candidate");
                    }

                    if (polyline.Closed && longSide >= 500 && longSide <= 2500 && shortSide >= 60 && shortSide <= 600)
                    {
                        semanticHints.Add("window_or_door_candidate");
                    }
                }
                else if (!polyline.Closed && polyline.Length >= 2000)
                {
                    semanticHints.Add("wall_path_candidate");
                }

                payload["semantic_hints"] = semanticHints;
                return payload;
            }

            Dimension dimension = entity as Dimension;
            if (dimension != null)
            {
                payload["measurement"] = Round(dimension.Measurement);
                payload["text"] = string.IsNullOrWhiteSpace(dimension.DimensionText) ? "<>" : dimension.DimensionText;
                semanticHints.Add("distance_annotation_candidate");
                payload["semantic_hints"] = semanticHints;
                return payload;
            }

            BlockReference blockReference = entity as BlockReference;
            if (blockReference != null)
            {
                string blockName = ResolveBlockName(transaction, blockReference);
                payload["name"] = blockName;
                payload["position"] = new[] { Round(blockReference.Position.X), Round(blockReference.Position.Y) };
                semanticHints.AddRange(GetBlockSemanticHints(blockName));
            }

            payload["semantic_hints"] = semanticHints;

            return payload;
        }

        private static IEnumerable<double[]> GetPolylinePreview(Polyline polyline)
        {
            List<double[]> preview = new List<double[]>();
            int count = Math.Min(polyline.NumberOfVertices, 8);
            for (int index = 0; index < count; index++)
            {
                Point2d point = polyline.GetPoint2dAt(index);
                preview.Add(new[] { Round(point.X), Round(point.Y) });
            }

            return preview;
        }

        private static bool IsRectangleCandidate(Polyline polyline)
        {
            if (polyline == null || !polyline.Closed || polyline.NumberOfVertices != 4)
            {
                return false;
            }

            const double tolerance = 1e-6;
            for (int index = 0; index < polyline.NumberOfVertices; index++)
            {
                Point2d current = polyline.GetPoint2dAt(index);
                Point2d next = polyline.GetPoint2dAt((index + 1) % polyline.NumberOfVertices);
                double dx = Math.Abs(next.X - current.X);
                double dy = Math.Abs(next.Y - current.Y);
                if (dx > tolerance && dy > tolerance)
                {
                    return false;
                }
            }

            return true;
        }

        private static IEnumerable<string> GetBlockSemanticHints(string blockName)
        {
            List<string> hints = new List<string>();
            string normalized = blockName ?? string.Empty;

            if (normalized.IndexOf("door", StringComparison.OrdinalIgnoreCase) >= 0 || normalized.Contains("门"))
            {
                hints.Add("door_block_candidate");
            }

            if (normalized.IndexOf("window", StringComparison.OrdinalIgnoreCase) >= 0 || normalized.Contains("窗"))
            {
                hints.Add("window_block_candidate");
            }

            if (normalized.IndexOf("wall", StringComparison.OrdinalIgnoreCase) >= 0 || normalized.Contains("墙"))
            {
                hints.Add("wall_block_candidate");
            }

            if (normalized.IndexOf("column", StringComparison.OrdinalIgnoreCase) >= 0 || normalized.Contains("柱"))
            {
                hints.Add("column_block_candidate");
            }

            return hints;
        }

        private static IEnumerable<string> GetSemanticHints(Dictionary<string, object> payload)
        {
            object value;
            if (!payload.TryGetValue("semantic_hints", out value))
            {
                return Enumerable.Empty<string>();
            }

            IEnumerable<string> list = value as IEnumerable<string>;
            return list ?? Enumerable.Empty<string>();
        }

        private static string GetLayerName(Dictionary<string, object> payload)
        {
            object value;
            return payload.TryGetValue("layer", out value) ? value as string : null;
        }

        private static double GetNumericMetric(Dictionary<string, object> payload, string key)
        {
            object value;
            if (!payload.TryGetValue(key, out value) || value == null)
            {
                return 0;
            }

            return Convert.ToDouble(value);
        }

        private static string ResolveBlockName(Transaction transaction, BlockReference blockReference)
        {
            try
            {
                ObjectId blockId = blockReference.DynamicBlockTableRecord != ObjectId.Null
                    ? blockReference.DynamicBlockTableRecord
                    : blockReference.BlockTableRecord;
                BlockTableRecord blockRecord = transaction.GetObject(blockId, OpenMode.ForRead) as BlockTableRecord;
                return blockRecord != null ? blockRecord.Name : string.Empty;
            }
            catch
            {
                return string.Empty;
            }
        }

        private static void MarkDirty(string commandName, string commandState)
        {
            lock (SyncObject)
            {
                _snapshotDirty = true;
                _lastCommandName = string.IsNullOrWhiteSpace(commandName) ? _lastCommandName : commandName;
                _lastCommandState = commandState;
                _lastChangeUtc = DateTime.UtcNow;
            }
        }

        private static string SafeGetDocumentName(Document document)
        {
            try
            {
                return !string.IsNullOrWhiteSpace(document.Name)
                    ? Path.GetFileName(document.Name)
                    : "未命名图纸";
            }
            catch
            {
                return "未命名图纸";
            }
        }

        private static string FormatTime(DateTime utcTime)
        {
            return utcTime == DateTime.MinValue
                ? "未记录"
                : utcTime.ToLocalTime().ToString("HH:mm:ss");
        }

        private static string Limit(string value, int maxLength)
        {
            if (string.IsNullOrWhiteSpace(value) || value.Length <= maxLength)
            {
                return value;
            }

            return value.Substring(0, maxLength) + " ...(truncated)";
        }

        private static double Round(double value)
        {
            return Math.Round(value, 2);
        }

        public sealed class DrawingContextSummary
        {
            public string DocumentName { get; set; }
            public string LastCommandName { get; set; }
            public string LastCommandState { get; set; }
            public string LastChangeText { get; set; }
            public string SnapshotRefreshText { get; set; }
            public int AppendedSinceRefresh { get; set; }
            public int ModifiedSinceRefresh { get; set; }
            public int ErasedSinceRefresh { get; set; }
            public int LayerCount { get; set; }
            public int EntityCount { get; set; }
            public int JsonSize { get; set; }
            public string SelectionSummaryJson { get; set; }
            public string SnapshotPreviewJson { get; set; }
        }

        private static void OnDocumentActivated(object sender, DocumentCollectionEventArgs e)
        {
            AttachToDocument(e != null ? e.Document : null);
        }

        private static void OnCommandWillStart(object sender, CommandEventArgs e)
        {
            lock (SyncObject)
            {
                _lastCommandName = e != null ? e.GlobalCommandName : _lastCommandName;
                _lastCommandState = "running";
                _lastChangeUtc = DateTime.UtcNow;
            }
        }

        private static void OnCommandEnded(object sender, CommandEventArgs e)
        {
            MarkDirty(e != null ? e.GlobalCommandName : null, "ended");
        }

        private static void OnCommandCancelled(object sender, CommandEventArgs e)
        {
            MarkDirty(e != null ? e.GlobalCommandName : null, "cancelled");
        }

        private static void OnCommandFailed(object sender, CommandEventArgs e)
        {
            MarkDirty(e != null ? e.GlobalCommandName : null, "failed");
        }

        private static void OnObjectAppended(object sender, ObjectEventArgs e)
        {
            lock (SyncObject)
            {
                _appendedSinceRefresh++;
                _snapshotDirty = true;
                _lastChangeUtc = DateTime.UtcNow;
            }
        }

        private static void OnObjectModified(object sender, ObjectEventArgs e)
        {
            lock (SyncObject)
            {
                _modifiedSinceRefresh++;
                _snapshotDirty = true;
                _lastChangeUtc = DateTime.UtcNow;
            }
        }

        private static void OnObjectErased(object sender, ObjectErasedEventArgs e)
        {
            lock (SyncObject)
            {
                if (e != null && e.Erased)
                {
                    _erasedSinceRefresh++;
                }

                _snapshotDirty = true;
                _lastChangeUtc = DateTime.UtcNow;
            }
        }
    }
}
