using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using AgentBridge.Core;
using Newtonsoft.Json;

namespace AgentBridge.Engine
{
    public class SnapshotResult
    {
        public int LayerCount { get; set; }

        public int EntityCount { get; set; }

        public int JsonSize { get; set; }

        public string L2Summary { get; set; }

        public string ToJson()
        {
            return L2Summary ?? "{}";
        }
    }

    public class SnapshotExtractor
    {
        public SnapshotResult ExtractL2Summary()
        {
            Document document = Application.DocumentManager.MdiActiveDocument;
            if (document == null)
            {
                return new SnapshotResult();
            }

            Database database = document.Database;
            Dictionary<string, LayerStat> layerStats = new Dictionary<string, LayerStat>(StringComparer.OrdinalIgnoreCase);
            Dictionary<string, int> blocks = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            List<TextInfo> texts = new List<TextInfo>();
            List<EntityInfo> entityInfos = new List<EntityInfo>();
            List<FrameCandidate> frameCandidates = new List<FrameCandidate>();
            Extents3d overallExtents = new Extents3d();
            bool hasExtents = false;
            int totalEntities = 0;

            using (Transaction transaction = database.TransactionManager.StartOpenCloseTransaction())
            {
                BlockTable blockTable = (BlockTable)transaction.GetObject(database.BlockTableId, OpenMode.ForRead);
                BlockTableRecord modelSpace = (BlockTableRecord)transaction.GetObject(blockTable[BlockTableRecord.ModelSpace], OpenMode.ForRead);

                foreach (ObjectId objectId in modelSpace)
                {
                    try
                    {
                        Entity entity = transaction.GetObject(objectId, OpenMode.ForRead) as Entity;
                        if (entity == null)
                        {
                            continue;
                        }

                        totalEntities++;
                        string layerName = string.IsNullOrWhiteSpace(entity.Layer) ? "0" : entity.Layer;
                        LayerStat stat;
                        if (!layerStats.TryGetValue(layerName, out stat))
                        {
                            stat = new LayerStat(layerName);
                            layerStats[layerName] = stat;
                        }

                        stat.Count++;
                        stat.Types.Add(entity.GetType().Name);

                        try
                        {
                            Extents3d extents = entity.GeometricExtents;
                            EntityInfo entityInfo = CreateEntityInfo(transaction, entity, layerName, extents);
                            entityInfos.Add(entityInfo);
                            stat.Expand(extents);
                            if (hasExtents)
                            {
                                overallExtents.AddExtents(extents);
                            }
                            else
                            {
                                overallExtents = extents;
                                hasExtents = true;
                            }

                            FrameCandidate frameCandidate = TryCreateFrameCandidate(entity, layerName, extents);
                            if (frameCandidate != null)
                            {
                                frameCandidates.Add(frameCandidate);
                            }
                        }
                        catch
                        {
                        }

                        DBText dbText = entity as DBText;
                        if (dbText != null)
                        {
                            texts.Add(new TextInfo
                            {
                                Handle = dbText.Handle.ToString(),
                                Content = dbText.TextString,
                                Layer = layerName,
                                Height = dbText.Height,
                                Position = Point(dbText.Position),
                                Rotation = dbText.Rotation,
                                TextStyle = ResolveTextStyleName(transaction, dbText.TextStyleId)
                            });
                        }

                        MText mText = entity as MText;
                        if (mText != null)
                        {
                            texts.Add(new TextInfo
                            {
                                Handle = mText.Handle.ToString(),
                                Content = mText.Text,
                                Layer = layerName,
                                Height = mText.TextHeight,
                                Position = Point(mText.Location),
                                Rotation = mText.Rotation,
                                TextStyle = ResolveTextStyleName(transaction, mText.TextStyleId)
                            });
                        }

                        BlockReference blockReference = entity as BlockReference;
                        if (blockReference != null)
                        {
                            string blockName = ResolveBlockName(transaction, blockReference);
                            if (!string.IsNullOrWhiteSpace(blockName))
                            {
                                blocks[blockName] = blocks.ContainsKey(blockName) ? blocks[blockName] + 1 : 1;
                            }
                        }
                    }
                    catch (Exception ex)
                    {
                        Logger.Warn("Failed to inspect entity: " + ex.Message);
                    }
                }

                transaction.Commit();
            }

            List<FrameAnalysis> frames = BuildFrameAnalyses(frameCandidates, entityInfos);
            HashSet<string> assignedEntityHandles = new HashSet<string>(frames.SelectMany(item => item.EntityHandles), StringComparer.OrdinalIgnoreCase);
            List<EntityInfo> outsideFrameEntities = entityInfos
                .Where(item => !item.IsFrameCandidate && !assignedEntityHandles.Contains(item.Handle))
                .ToList();

            object payload = new
            {
                drawing_summary = new
                {
                    total_entities = totalEntities,
                    total_layers = layerStats.Count,
                    detected_frames = frames.Count,
                    units = database.Insunits.ToString(),
                    bounds = hasExtents ? new
                    {
                        min = new[] { Math.Round(overallExtents.MinPoint.X), Math.Round(overallExtents.MinPoint.Y) },
                        max = new[] { Math.Round(overallExtents.MaxPoint.X), Math.Round(overallExtents.MaxPoint.Y) }
                    } : null
                },
                layers = layerStats.Values.OrderBy(item => item.Name).Select(item => new
                {
                    name = item.Name,
                    semantic_group = GetSemanticLayerGroup(item.Name),
                    count = item.Count,
                    types = item.Types.OrderBy(type => type).ToArray(),
                    bounds = item.HasExtents ? new
                    {
                        min = new[] { Math.Round(item.MinX), Math.Round(item.MinY) },
                        max = new[] { Math.Round(item.MaxX), Math.Round(item.MaxY) }
                    } : null
                }).ToArray(),
                texts = texts.Take(2000).Select(item => new
                {
                    handle = item.Handle,
                    content = item.Content,
                    position = item.Position,
                    layer = item.Layer,
                    height = item.Height,
                    rotation = item.Rotation,
                    text_style = item.TextStyle
                }).ToArray(),
                blocks = blocks.OrderBy(item => item.Key).Select(item => new { name = item.Key, insertions = item.Value }).ToArray(),
                entities = entityInfos.Take(5000).Select(ToSnapshotEntity).ToArray(),
                entities_truncated = entityInfos.Count > 5000,
                dimensions = entityInfos.Where(item => item.TypeName.IndexOf("Dimension", StringComparison.OrdinalIgnoreCase) >= 0).Take(1000).Select(ToSnapshotEntity).ToArray(),
                frames = frames.Select(item => new
                {
                    index = item.Index,
                    layer = item.Layer,
                    width = Round(item.Width),
                    height = Round(item.Height),
                    area = Round(item.Area),
                    bounds = new
                    {
                        min = new[] { Round(item.MinX), Round(item.MinY) },
                        max = new[] { Round(item.MaxX), Round(item.MaxY) }
                    },
                    dominant_layers = item.DominantLayers,
                    dominant_types = item.DominantTypes,
                    text_count = item.TextCount,
                    sample_texts = item.SampleTexts,
                    title_block_texts = item.TitleBlockTexts,
                    blocks = item.BlockNames,
                    semantic_hints = item.SemanticHints,
                    contained_entities = item.EntityCount
                }).ToArray(),
                outside_frames = BuildOutsideFrameSummary(outsideFrameEntities)
            };

            string json = JsonConvert.SerializeObject(payload, Formatting.None);
            return new SnapshotResult
            {
                LayerCount = layerStats.Count,
                EntityCount = totalEntities,
                JsonSize = json.Length,
                L2Summary = json
            };
        }

        private static string ResolveBlockName(Transaction transaction, BlockReference blockReference)
        {
            ObjectId blockId = blockReference.DynamicBlockTableRecord != ObjectId.Null
                ? blockReference.DynamicBlockTableRecord
                : blockReference.BlockTableRecord;
            BlockTableRecord record = transaction.GetObject(blockId, OpenMode.ForRead) as BlockTableRecord;
            return record != null ? record.Name : null;
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

        private static EntityInfo CreateEntityInfo(Transaction transaction, Entity entity, string layerName, Extents3d extents)
        {
            string textContent = null;
            string blockName = null;
            string effectiveName = null;
            double[] start = null;
            double[] end = null;
            double[] center = null;
            double[] position = null;
            double[][] points = null;
            bool? closed = null;
            double? radius = null;
            double? startAngle = null;
            double? endAngle = null;
            double? rotation = null;
            double[] scale = null;
            double? height = null;
            string textStyle = null;
            double? measurement = null;
            Dictionary<string, string> attributes = null;
            string runtimeType = entity.GetType().FullName ?? entity.GetType().Name;
            string objectClass = null;
            string dxfName = null;
            try
            {
                Autodesk.AutoCAD.Runtime.RXClass rxClass = entity.GetRXClass();
                if (rxClass != null)
                {
                    objectClass = rxClass.Name;
                    dxfName = rxClass.DxfName;
                }
            }
            catch
            {
            }
            bool isProxy = ContainsIgnoreCase(runtimeType, "proxy")
                || ContainsIgnoreCase(objectClass, "proxy")
                || ContainsIgnoreCase(dxfName, "proxy");
            bool isCustomObject = !string.Equals(
                entity.GetType().Namespace,
                typeof(Entity).Namespace,
                StringComparison.Ordinal);

            Line line = entity as Line;
            if (line != null)
            {
                start = Point(line.StartPoint);
                end = Point(line.EndPoint);
            }

            Polyline polyline = entity as Polyline;
            if (polyline != null)
            {
                points = Enumerable.Range(0, polyline.NumberOfVertices)
                    .Select(index => Point(polyline.GetPoint2dAt(index)))
                    .ToArray();
                closed = polyline.Closed;
            }

            Arc arc = entity as Arc;
            if (arc != null)
            {
                center = Point(arc.Center);
                radius = arc.Radius;
                startAngle = arc.StartAngle;
                endAngle = arc.EndAngle;
                start = Point(arc.StartPoint);
                end = Point(arc.EndPoint);
            }

            Circle circle = entity as Circle;
            if (circle != null)
            {
                center = Point(circle.Center);
                radius = circle.Radius;
            }

            DBText dbText = entity as DBText;
            if (dbText != null)
            {
                textContent = dbText.TextString;
                position = Point(dbText.Position);
                height = dbText.Height;
                rotation = dbText.Rotation;
                textStyle = ResolveTextStyleName(transaction, dbText.TextStyleId);
            }

            MText mText = entity as MText;
            if (mText != null)
            {
                textContent = mText.Text;
                position = Point(mText.Location);
                height = mText.TextHeight;
                rotation = mText.Rotation;
                textStyle = ResolveTextStyleName(transaction, mText.TextStyleId);
            }

            BlockReference blockReference = entity as BlockReference;
            if (blockReference != null)
            {
                blockName = blockReference.Name;
                effectiveName = ResolveBlockName(transaction, blockReference);
                position = Point(blockReference.Position);
                rotation = blockReference.Rotation;
                scale = new[] { Round(blockReference.ScaleFactors.X), Round(blockReference.ScaleFactors.Y), Round(blockReference.ScaleFactors.Z) };
                attributes = ResolveAttributes(transaction, blockReference);
            }

            Dimension dimension = entity as Dimension;
            if (dimension != null)
            {
                position = Point(dimension.TextPosition);
                textContent = dimension.DimensionText;
                try
                {
                    measurement = dimension.Measurement;
                }
                catch
                {
                }
            }

            return new EntityInfo
            {
                Handle = entity.Handle.ToString(),
                Layer = layerName,
                TypeName = entity.GetType().Name,
                RuntimeType = runtimeType,
                ObjectClass = objectClass,
                DxfName = dxfName,
                IsProxy = isProxy,
                IsCustomObject = isCustomObject,
                ObjectEnablerStatus = isProxy
                    ? "missing_or_incompatible"
                    : (isCustomObject ? "adapter_required" : "native"),
                MinX = extents.MinPoint.X,
                MinY = extents.MinPoint.Y,
                MaxX = extents.MaxPoint.X,
                MaxY = extents.MaxPoint.Y,
                TextContent = textContent,
                BlockName = blockName,
                EffectiveName = effectiveName,
                Start = start,
                End = end,
                Center = center,
                Position = position,
                Points = points,
                Closed = closed,
                Radius = radius,
                StartAngle = startAngle,
                EndAngle = endAngle,
                Rotation = rotation,
                Scale = scale,
                Height = height,
                TextStyle = textStyle,
                Measurement = measurement,
                Attributes = attributes,
                IsFrameCandidate = entity is Polyline && IsRectangularClosedPolyline(entity as Polyline)
            };
        }

        private static object ToSnapshotEntity(EntityInfo item)
        {
            return new
            {
                handle = item.Handle,
                type = item.TypeName,
                runtime_type = item.RuntimeType,
                object_class = item.ObjectClass,
                dxf_name = item.DxfName,
                is_proxy = item.IsProxy,
                is_custom_object = item.IsCustomObject,
                object_enabler_status = item.ObjectEnablerStatus,
                layer = item.Layer,
                start = item.Start,
                end = item.End,
                center = item.Center,
                position = item.Position,
                points = item.Points,
                closed = item.Closed,
                radius = item.Radius,
                start_angle = item.StartAngle,
                end_angle = item.EndAngle,
                rotation = item.Rotation,
                scale = item.Scale,
                block_name = item.BlockName,
                effective_name = item.EffectiveName,
                attributes = item.Attributes,
                content = item.TextContent,
                height = item.Height,
                text_style = item.TextStyle,
                measurement = item.Measurement,
                bounds = new
                {
                    min = new[] { Round(item.MinX), Round(item.MinY) },
                    max = new[] { Round(item.MaxX), Round(item.MaxY) }
                }
            };
        }

        private static bool ContainsIgnoreCase(string value, string token)
        {
            return !string.IsNullOrWhiteSpace(value)
                && value.IndexOf(token, StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private static Dictionary<string, string> ResolveAttributes(Transaction transaction, BlockReference blockReference)
        {
            Dictionary<string, string> attributes = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (ObjectId attributeId in blockReference.AttributeCollection)
            {
                AttributeReference attribute = transaction.GetObject(attributeId, OpenMode.ForRead) as AttributeReference;
                if (attribute != null && !string.IsNullOrWhiteSpace(attribute.Tag))
                {
                    attributes[attribute.Tag] = attribute.TextString ?? string.Empty;
                }
            }

            return attributes.Count > 0 ? attributes : null;
        }

        private static string ResolveTextStyleName(Transaction transaction, ObjectId textStyleId)
        {
            try
            {
                TextStyleTableRecord record = transaction.GetObject(textStyleId, OpenMode.ForRead) as TextStyleTableRecord;
                return record != null ? record.Name : null;
            }
            catch
            {
                return null;
            }
        }

        private static double[] Point(Point3d point)
        {
            return new[] { Round(point.X), Round(point.Y) };
        }

        private static double[] Point(Point2d point)
        {
            return new[] { Round(point.X), Round(point.Y) };
        }

        private static FrameCandidate TryCreateFrameCandidate(Entity entity, string layerName, Extents3d extents)
        {
            Polyline polyline = entity as Polyline;
            if (polyline == null || !IsRectangularClosedPolyline(polyline))
            {
                return null;
            }

            double width = Math.Abs(extents.MaxPoint.X - extents.MinPoint.X);
            double height = Math.Abs(extents.MaxPoint.Y - extents.MinPoint.Y);
            if (width < 1000 || height < 1000)
            {
                return null;
            }

            return new FrameCandidate
            {
                Handle = entity.Handle.ToString(),
                Layer = layerName,
                MinX = extents.MinPoint.X,
                MinY = extents.MinPoint.Y,
                MaxX = extents.MaxPoint.X,
                MaxY = extents.MaxPoint.Y
            };
        }

        private static bool IsRectangularClosedPolyline(Polyline polyline)
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

        private static List<FrameAnalysis> BuildFrameAnalyses(List<FrameCandidate> frameCandidates, List<EntityInfo> entityInfos)
        {
            List<FrameCandidate> promotedFrames = frameCandidates
                .Where(candidate => IsPromotableFrame(candidate, entityInfos))
                .OrderBy(candidate => candidate.Area)
                .ToList();

            Dictionary<string, FrameCandidate> entityAssignments = new Dictionary<string, FrameCandidate>(StringComparer.OrdinalIgnoreCase);
            foreach (EntityInfo entity in entityInfos.Where(item => !item.IsFrameCandidate))
            {
                FrameCandidate owner = promotedFrames.FirstOrDefault(candidate => Contains(candidate, entity));
                if (owner != null)
                {
                    entityAssignments[entity.Handle] = owner;
                }
            }

            List<FrameAnalysis> analyses = new List<FrameAnalysis>();
            int index = 1;
            foreach (FrameCandidate candidate in promotedFrames.OrderByDescending(item => item.Area))
            {
                List<EntityInfo> contained = entityAssignments
                    .Where(item => string.Equals(item.Value.Handle, candidate.Handle, StringComparison.OrdinalIgnoreCase))
                    .Select(item => entityInfos.First(entity => string.Equals(entity.Handle, item.Key, StringComparison.OrdinalIgnoreCase)))
                    .ToList();

                if (contained.Count == 0)
                {
                    continue;
                }

                analyses.Add(new FrameAnalysis
                {
                    Index = index++,
                    Layer = candidate.Layer,
                    MinX = candidate.MinX,
                    MinY = candidate.MinY,
                    MaxX = candidate.MaxX,
                    MaxY = candidate.MaxY,
                    Width = candidate.Width,
                    Height = candidate.Height,
                    Area = candidate.Area,
                    EntityCount = contained.Count,
                    TextCount = contained.Count(item => !string.IsNullOrWhiteSpace(item.TextContent)),
                    DominantLayers = contained.GroupBy(item => item.Layer).OrderByDescending(group => group.Count()).Take(5).Select(group => group.Key).ToArray(),
                    DominantTypes = contained.GroupBy(item => item.TypeName).OrderByDescending(group => group.Count()).Take(5).Select(group => group.Key).ToArray(),
                    SampleTexts = contained.Where(item => !string.IsNullOrWhiteSpace(item.TextContent)).Select(item => item.TextContent).Distinct().Take(8).ToArray(),
                    TitleBlockTexts = contained.Where(item => !string.IsNullOrWhiteSpace(item.TextContent) && IsTitleBlockText(candidate, item)).Select(item => item.TextContent).Distinct().Take(8).ToArray(),
                    BlockNames = contained.Where(item => !string.IsNullOrWhiteSpace(item.BlockName)).Select(item => item.BlockName).Distinct().Take(8).ToArray(),
                    SemanticHints = BuildFrameSemanticHints(candidate, contained),
                    EntityHandles = contained.Select(item => item.Handle).ToArray()
                });
            }

            return analyses;
        }

        private static bool IsPromotableFrame(FrameCandidate candidate, List<EntityInfo> entityInfos)
        {
            List<EntityInfo> contained = entityInfos.Where(item => !item.IsFrameCandidate && Contains(candidate, item)).ToList();
            int textCount = contained.Count(item => !string.IsNullOrWhiteSpace(item.TextContent));
            return contained.Count >= 3 || (contained.Count >= 2 && textCount >= 1);
        }

        private static bool Contains(FrameCandidate frame, EntityInfo entity)
        {
            double centerX = (entity.MinX + entity.MaxX) / 2.0;
            double centerY = (entity.MinY + entity.MaxY) / 2.0;
            return centerX >= frame.MinX && centerX <= frame.MaxX && centerY >= frame.MinY && centerY <= frame.MaxY;
        }

        private static bool IsTitleBlockText(FrameCandidate frame, EntityInfo entity)
        {
            double centerX = (entity.MinX + entity.MaxX) / 2.0;
            double centerY = (entity.MinY + entity.MaxY) / 2.0;
            double lowerBand = frame.MinY + frame.Height * 0.2;
            double rightBand = frame.MinX + frame.Width * 0.55;
            return centerY <= lowerBand || centerX >= rightBand;
        }

        private static string[] BuildFrameSemanticHints(FrameCandidate frame, List<EntityInfo> contained)
        {
            List<string> hints = new List<string>();
            string allTexts = string.Join(" ", contained.Where(item => !string.IsNullOrWhiteSpace(item.TextContent)).Select(item => item.TextContent));
            int dimensionCount = contained.Count(item => string.Equals(item.TypeName, nameof(AlignedDimension), StringComparison.OrdinalIgnoreCase) || item.TypeName.IndexOf("Dimension", StringComparison.OrdinalIgnoreCase) >= 0);
            int lineLikeCount = contained.Count(item => item.TypeName.IndexOf("Line", StringComparison.OrdinalIgnoreCase) >= 0 || item.TypeName.IndexOf("Polyline", StringComparison.OrdinalIgnoreCase) >= 0);

            hints.Add("drawing_frame_candidate");

            if (allTexts.IndexOf("平面", StringComparison.OrdinalIgnoreCase) >= 0 || allTexts.IndexOf("PLAN", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                hints.Add("plan_view_candidate");
            }

            if (allTexts.IndexOf("立面", StringComparison.OrdinalIgnoreCase) >= 0 || allTexts.IndexOf("ELEV", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                hints.Add("elevation_candidate");
            }

            if (allTexts.IndexOf("剖面", StringComparison.OrdinalIgnoreCase) >= 0 || allTexts.IndexOf("SECTION", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                hints.Add("section_candidate");
            }

            if (lineLikeCount >= 6 && dimensionCount >= 1)
            {
                hints.Add("geometry_with_dimensions_candidate");
            }

            if (contained.Count(item => !string.IsNullOrWhiteSpace(item.TextContent)) >= 10)
            {
                hints.Add("text_dense_frame_candidate");
            }

            if (frame.Area >= 10000000)
            {
                hints.Add("large_sheet_candidate");
            }

            return hints.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        }

        private static object BuildOutsideFrameSummary(List<EntityInfo> outsideFrameEntities)
        {
            return new
            {
                entity_count = outsideFrameEntities.Count,
                dominant_layers = outsideFrameEntities.GroupBy(item => item.Layer).OrderByDescending(group => group.Count()).Take(5).Select(group => group.Key).ToArray(),
                dominant_types = outsideFrameEntities.GroupBy(item => item.TypeName).OrderByDescending(group => group.Count()).Take(5).Select(group => group.Key).ToArray(),
                sample_texts = outsideFrameEntities.Where(item => !string.IsNullOrWhiteSpace(item.TextContent)).Select(item => item.TextContent).Distinct().Take(8).ToArray(),
                blocks = outsideFrameEntities.Where(item => !string.IsNullOrWhiteSpace(item.BlockName)).Select(item => item.BlockName).Distinct().Take(8).ToArray()
            };
        }

        private static double Round(double value)
        {
            return Math.Round(value, 2);
        }

        private sealed class LayerStat
        {
            public LayerStat(string name)
            {
                Name = name;
                Types = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                MinX = double.MaxValue;
                MinY = double.MaxValue;
                MaxX = double.MinValue;
                MaxY = double.MinValue;
            }

            public string Name { get; private set; }

            public int Count { get; set; }

            public HashSet<string> Types { get; private set; }

            public double MinX { get; private set; }

            public double MinY { get; private set; }

            public double MaxX { get; private set; }

            public double MaxY { get; private set; }

            public bool HasExtents { get; private set; }

            public void Expand(Extents3d extents)
            {
                HasExtents = true;
                MinX = Math.Min(MinX, extents.MinPoint.X);
                MinY = Math.Min(MinY, extents.MinPoint.Y);
                MaxX = Math.Max(MaxX, extents.MaxPoint.X);
                MaxY = Math.Max(MaxY, extents.MaxPoint.Y);
            }
        }

        private sealed class TextInfo
        {
            public string Handle { get; set; }

            public string Content { get; set; }

            public double[] Position { get; set; }

            public string Layer { get; set; }

            public double Height { get; set; }

            public double Rotation { get; set; }

            public string TextStyle { get; set; }
        }

        private sealed class EntityInfo
        {
            public string Handle { get; set; }

            public string Layer { get; set; }

            public string TypeName { get; set; }

            public string RuntimeType { get; set; }

            public string ObjectClass { get; set; }

            public string DxfName { get; set; }

            public bool IsProxy { get; set; }

            public bool IsCustomObject { get; set; }

            public string ObjectEnablerStatus { get; set; }

            public double MinX { get; set; }

            public double MinY { get; set; }

            public double MaxX { get; set; }

            public double MaxY { get; set; }

            public string TextContent { get; set; }

            public string BlockName { get; set; }

            public string EffectiveName { get; set; }

            public double[] Start { get; set; }

            public double[] End { get; set; }

            public double[] Center { get; set; }

            public double[] Position { get; set; }

            public double[][] Points { get; set; }

            public bool? Closed { get; set; }

            public double? Radius { get; set; }

            public double? StartAngle { get; set; }

            public double? EndAngle { get; set; }

            public double? Rotation { get; set; }

            public double[] Scale { get; set; }

            public double? Height { get; set; }

            public string TextStyle { get; set; }

            public double? Measurement { get; set; }

            public Dictionary<string, string> Attributes { get; set; }

            public bool IsFrameCandidate { get; set; }
        }

        private sealed class FrameCandidate
        {
            public string Handle { get; set; }

            public string Layer { get; set; }

            public double MinX { get; set; }

            public double MinY { get; set; }

            public double MaxX { get; set; }

            public double MaxY { get; set; }

            public double Width => Math.Abs(MaxX - MinX);

            public double Height => Math.Abs(MaxY - MinY);

            public double Area => Width * Height;
        }

        private sealed class FrameAnalysis
        {
            public int Index { get; set; }

            public string Layer { get; set; }

            public double MinX { get; set; }

            public double MinY { get; set; }

            public double MaxX { get; set; }

            public double MaxY { get; set; }

            public double Width { get; set; }

            public double Height { get; set; }

            public double Area { get; set; }

            public int EntityCount { get; set; }

            public int TextCount { get; set; }

            public string[] DominantLayers { get; set; }

            public string[] DominantTypes { get; set; }

            public string[] SampleTexts { get; set; }

            public string[] TitleBlockTexts { get; set; }

            public string[] BlockNames { get; set; }

            public string[] SemanticHints { get; set; }

            public string[] EntityHandles { get; set; }
        }
    }
}
