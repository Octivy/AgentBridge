using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using AgentBridge.Core;
using AgentBridge.LLM;

namespace AgentBridge.Engine
{
    public sealed class CadCommandCommitResult
    {
        public IReadOnlyList<string> EntityHandles { get; set; }

        public int EntityCount { get; set; }

        public bool Verified { get; set; }

        public string RollbackToken { get; set; }

        public bool RollbackSupported { get; set; }
    }

    public sealed class CadCommandRollbackDescription
    {
        public string RollbackToken { get; set; }

        public IReadOnlyList<string> EntityHandles { get; set; }

        public int EntityCount { get; set; }
    }

    public class CommandExecutor
    {
        private const int MaxRollbackRecords = 256;
        private static readonly object RollbackSync = new object();
        private static readonly Dictionary<string, CadRollbackRecord> RollbackRecords = new Dictionary<string, CadRollbackRecord>(StringComparer.Ordinal);
        private static readonly Queue<string> RollbackOrder = new Queue<string>();

        public static List<string> Validate(List<DrawCommand> commands)
        {
            List<string> errors = new List<string>();
            if (commands == null || commands.Count == 0)
            {
                errors.Add("commands array is empty.");
                return errors;
            }

            for (int index = 0; index < commands.Count; index++)
            {
                string error = ValidateSingle(commands[index]);
                if (!string.IsNullOrWhiteSpace(error))
                {
                    errors.Add("commands[" + index + "]: " + error);
                }
            }

            return errors;
        }

        public static int Execute(List<DrawCommand> commands)
        {
            if (commands == null || commands.Count == 0)
            {
                return 0;
            }

            commands = FilterValidCommands(commands);
            if (commands.Count == 0)
            {
                Logger.Warn("No valid draw commands to execute.");
                return 0;
            }

            Document document = Application.DocumentManager.MdiActiveDocument;
            if (document == null)
            {
                return 0;
            }

            int successCount = 0;

            using (DocumentLock documentLock = document.LockDocument())
            using (Transaction transaction = document.Database.TransactionManager.StartTransaction())
            {
                BlockTableRecord currentSpace = (BlockTableRecord)transaction.GetObject(document.Database.CurrentSpaceId, OpenMode.ForWrite);

                foreach (DrawCommand command in commands)
                {
                    try
                    {
                        if (ExecuteSingle(transaction, document.Database, currentSpace, command))
                        {
                            successCount++;
                        }
                    }
                    catch (Exception ex)
                    {
                        Logger.Warn("Command execution failed for " + command.Type + ": " + ex.Message);
                    }
                }

                transaction.Commit();
            }

            document.Editor.Regen();
            return successCount;
        }

        public static CadCommandCommitResult ExecuteAtomic(List<DrawCommand> commands)
        {
            return ExecuteAtomic(commands, null, null, null);
        }

        public static CadCommandCommitResult ExecuteAtomic(
            List<DrawCommand> commands,
            Action<Database, Transaction, IReadOnlyList<string>> commitAction,
            Func<Database, bool> verifyAction,
            Action<Database, Transaction> rollbackAction)
        {
            List<string> errors = Validate(commands);
            if (errors.Count > 0)
            {
                throw new ArgumentException(string.Join(" ", errors));
            }

            Document document = Application.DocumentManager.MdiActiveDocument;
            if (document == null)
            {
                throw new InvalidOperationException("No active AutoCAD document.");
            }

            List<string> handles = new List<string>();
            using (DocumentLock documentLock = document.LockDocument())
            using (Transaction transaction = document.Database.TransactionManager.StartTransaction())
            {
                BlockTableRecord currentSpace = (BlockTableRecord)transaction.GetObject(document.Database.CurrentSpaceId, OpenMode.ForWrite);
                foreach (DrawCommand command in commands)
                {
                    if (!ExecuteSingle(transaction, document.Database, currentSpace, command, handles))
                    {
                        throw new InvalidOperationException("CAD command did not create an entity: " + command.Type);
                    }
                }

                commitAction?.Invoke(document.Database, transaction, handles.AsReadOnly());

                transaction.Commit();
            }

            document.Editor.Regen();
            bool verified = VerifyEntities(document.Database, handles, expectErased: false)
                && (verifyAction == null || verifyAction(document.Database));
            if (!verified)
            {
                CleanupFailedCommit(document, handles, rollbackAction);
                throw new InvalidOperationException("CAD commit verification failed and the unverified changes were removed.");
            }

            string rollbackToken = StoreRollback(document.Database, handles, rollbackAction);
            return new CadCommandCommitResult
            {
                EntityHandles = handles.AsReadOnly(),
                EntityCount = handles.Count,
                Verified = verified,
                RollbackToken = rollbackToken,
                RollbackSupported = verified && !string.IsNullOrWhiteSpace(rollbackToken)
            };
        }

        public static CadCommandRollbackDescription DescribeRollback(string rollbackToken)
        {
            CadRollbackRecord record = GetRollbackRecord(rollbackToken);
            return new CadCommandRollbackDescription
            {
                RollbackToken = rollbackToken,
                EntityHandles = record.EntityHandles.AsReadOnly(),
                EntityCount = record.EntityHandles.Count
            };
        }

        public static string RegisterMutationRollback(
            Database database,
            IEnumerable<string> entityHandles,
            Action<Database, Transaction> rollbackAction)
        {
            if (database == null)
            {
                throw new ArgumentNullException(nameof(database));
            }

            List<string> handles = (entityHandles ?? Enumerable.Empty<string>())
                .Where(handle => !string.IsNullOrWhiteSpace(handle))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();
            if (handles.Count == 0 || rollbackAction == null)
            {
                return null;
            }

            return StoreRollback(database, handles, rollbackAction, eraseEntitiesOnRollback: false);
        }

        public static CadCommandCommitResult RollbackAtomic(Document document, string rollbackToken)
        {
            if (document == null)
            {
                throw new ArgumentNullException(nameof(document));
            }

            CadRollbackRecord record = GetRollbackRecord(rollbackToken);
            if (!string.Equals(record.DatabaseId, document.Database.FingerprintGuid.ToString(), StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Rollback token belongs to a different drawing.");
            }

            using (DocumentLock documentLock = document.LockDocument())
            using (Transaction transaction = document.Database.TransactionManager.StartTransaction())
            {
                foreach (string handle in record.EntityHandles)
                {
                    Entity entity = OpenEntityByHandle(document.Database, transaction, handle, OpenMode.ForWrite);
                    if (entity == null || entity.IsErased)
                    {
                        throw new InvalidOperationException("A committed entity changed or no longer exists; rollback was rejected.");
                    }

                    string expectedSignature;
                    if (!record.EntitySignatures.TryGetValue(handle, out expectedSignature)
                        || !string.Equals(expectedSignature, EntitySignature(entity), StringComparison.Ordinal))
                    {
                        throw new InvalidOperationException("A committed entity was edited after creation; rollback was rejected to preserve newer work.");
                    }

                    if (record.EraseEntitiesOnRollback)
                    {
                        entity.Erase();
                    }
                }

                record.RollbackAction?.Invoke(document.Database, transaction);

                transaction.Commit();
            }

            document.Editor.Regen();
            bool verified = VerifyEntities(
                document.Database,
                record.EntityHandles,
                expectErased: record.EraseEntitiesOnRollback);
            if (verified)
            {
                lock (RollbackSync)
                {
                    RollbackRecords.Remove(rollbackToken);
                }
            }

            return new CadCommandCommitResult
            {
                EntityHandles = record.EntityHandles.AsReadOnly(),
                EntityCount = record.EntityHandles.Count,
                Verified = verified,
                RollbackToken = null,
                RollbackSupported = false
            };
        }

        private static bool ExecuteSingle(Transaction transaction, Database database, BlockTableRecord currentSpace, DrawCommand command)
        {
            return ExecuteSingle(transaction, database, currentSpace, command, null);
        }

        private static bool ExecuteSingle(
            Transaction transaction,
            Database database,
            BlockTableRecord currentSpace,
            DrawCommand command,
            List<string> createdHandles)
        {
            if (command == null || string.IsNullOrWhiteSpace(command.Type))
            {
                return false;
            }

            DrawingTools.EnsureLayer(transaction, database, command.Layer, command.Color);

            Entity entity = null;
            switch (command.Type.Trim().ToUpperInvariant())
            {
                case "LINE":
                    entity = CreateLine(command);
                    break;
                case "POLYLINE":
                    entity = CreatePolyline(command);
                    break;
                case "RECTANGLE":
                case "RECT":
                    entity = CreateRectangle(command);
                    break;
                case "CIRCLE":
                    entity = CreateCircle(command);
                    break;
                case "ARC":
                    entity = CreateArc(command);
                    break;
                case "TEXT":
                    entity = CreateText(command);
                    break;
                case "DIMENSION":
                case "DIM":
                    entity = CreateDimension(command);
                    break;
                case "BLOCK_INSERT":
                case "INSERT":
                    entity = CreateBlockReference(transaction, database, command);
                    break;
                case "HATCH":
                    return CreateHatch(transaction, currentSpace, command, createdHandles);
                default:
                    Logger.Warn("Unsupported command type: " + command.Type);
                    return false;
            }

            if (entity == null)
            {
                return false;
            }

            if (!string.IsNullOrWhiteSpace(command.Layer))
            {
                entity.Layer = command.Layer;
            }

            if (command.Color.HasValue && command.Color.Value > 0)
            {
                entity.ColorIndex = (short)command.Color.Value;
            }

            currentSpace.AppendEntity(entity);
            transaction.AddNewlyCreatedDBObject(entity, true);
            if (createdHandles != null)
            {
                createdHandles.Add(entity.Handle.ToString());
            }
            return true;
        }

        private static List<DrawCommand> FilterValidCommands(List<DrawCommand> commands)
        {
            List<DrawCommand> valid = new List<DrawCommand>();
            for (int index = 0; index < commands.Count; index++)
            {
                DrawCommand command = commands[index];
                string error = ValidateSingle(command);
                if (string.IsNullOrWhiteSpace(error))
                {
                    valid.Add(command);
                }
                else
                {
                    Logger.Warn("Skipped invalid draw command " + index + ": " + error);
                }
            }

            return valid;
        }

        private static string ValidateSingle(DrawCommand command)
        {
            if (command == null)
            {
                return "command is null.";
            }

            if (string.IsNullOrWhiteSpace(command.Type))
            {
                return "type is required.";
            }

            if (!IsLayerNameAllowed(command.Layer))
            {
                return "layer name contains unsupported characters.";
            }

            if (command.Color.HasValue && (command.Color.Value < 1 || command.Color.Value > 255))
            {
                return "color must be between 1 and 255.";
            }

            string type = command.Type.Trim().ToUpperInvariant();
            switch (type)
            {
                case "LINE":
                    return ValidatePointPair(command.Start, command.End, "start/end");
                case "POLYLINE":
                    return ValidatePointArray(command.Points, 2, "points");
                case "RECTANGLE":
                case "RECT":
                    return ValidatePointPair(command.Start, command.End, "start/end");
                case "CIRCLE":
                    return ValidateRadiusShape(command.Center, command.Radius, "center/radius");
                case "ARC":
                    return ValidateRadiusShape(command.Center, command.Radius, "center/radius");
                case "TEXT":
                    if (string.IsNullOrWhiteSpace(command.Content))
                    {
                        return "content is required.";
                    }

                    if (command.Height.HasValue && (!IsFinite(command.Height.Value) || command.Height.Value <= 0))
                    {
                        return "height must be a positive number.";
                    }

                    return ValidatePoint(command.Position, "position");
                case "DIMENSION":
                case "DIM":
                    return ValidatePointPair(command.Start, command.End, "start/end");
                case "BLOCK_INSERT":
                case "INSERT":
                    if (string.IsNullOrWhiteSpace(command.Name))
                    {
                        return "block name is required.";
                    }

                    if (command.Scale.HasValue && (!IsFinite(command.Scale.Value) || command.Scale.Value <= 0))
                    {
                        return "scale must be a positive number.";
                    }

                    return ValidatePoint(command.Position, "position");
                case "HATCH":
                    return ValidatePointArray(command.Boundary, 3, "boundary");
                default:
                    return "unsupported command type: " + command.Type;
            }
        }

        private static string ValidatePointPair(double[] start, double[] end, string label)
        {
            string startError = ValidatePoint(start, "start");
            if (!string.IsNullOrWhiteSpace(startError))
            {
                return label + " invalid: " + startError;
            }

            string endError = ValidatePoint(end, "end");
            return string.IsNullOrWhiteSpace(endError) ? string.Empty : label + " invalid: " + endError;
        }

        private static string ValidateRadiusShape(double[] center, double? radius, string label)
        {
            string centerError = ValidatePoint(center, "center");
            if (!string.IsNullOrWhiteSpace(centerError))
            {
                return label + " invalid: " + centerError;
            }

            if (!radius.HasValue || !IsFinite(radius.Value) || radius.Value <= 0)
            {
                return label + " invalid: radius must be a positive number.";
            }

            return string.Empty;
        }

        private static string ValidatePointArray(double[][] points, int minimumCount, string label)
        {
            if (points == null || points.Length < minimumCount)
            {
                return label + " must contain at least " + minimumCount + " points.";
            }

            for (int index = 0; index < points.Length; index++)
            {
                string error = ValidatePoint(points[index], label + "[" + index + "]");
                if (!string.IsNullOrWhiteSpace(error))
                {
                    return error;
                }
            }

            return string.Empty;
        }

        private static string ValidatePoint(double[] point, string label)
        {
            if (point == null || point.Length < 2)
            {
                return label + " must contain at least x and y.";
            }

            if (!IsFinite(point[0]) || !IsFinite(point[1]) || (point.Length > 2 && !IsFinite(point[2])))
            {
                return label + " contains a non-finite coordinate.";
            }

            return string.Empty;
        }

        private static bool IsLayerNameAllowed(string layerName)
        {
            if (string.IsNullOrWhiteSpace(layerName))
            {
                return true;
            }

            string value = layerName.Trim();
            if (value.Length > 255)
            {
                return false;
            }

            char[] unsupported = new[] { '<', '>', '/', '\\', '"', ':', ';', '?', '*', '|', ',', '=', '`' };
            return value.IndexOfAny(unsupported) < 0;
        }

        private static bool IsFinite(double value)
        {
            return !double.IsNaN(value) && !double.IsInfinity(value);
        }

        private static Line CreateLine(DrawCommand command)
        {
            return command.Start != null && command.End != null
                ? new Line(DrawingTools.ToPoint3d(command.Start), DrawingTools.ToPoint3d(command.End))
                : null;
        }

        private static Polyline CreatePolyline(DrawCommand command)
        {
            if (command.Points == null || command.Points.Length < 2)
            {
                return null;
            }

            Polyline polyline = new Polyline(command.Points.Length);
            for (int index = 0; index < command.Points.Length; index++)
            {
                polyline.AddVertexAt(index, DrawingTools.ToPoint2d(command.Points[index]), 0, 0, 0);
            }

            polyline.Closed = command.Closed ?? false;
            return polyline;
        }

        private static Polyline CreateRectangle(DrawCommand command)
        {
            if (command.Start == null || command.End == null)
            {
                return null;
            }

            double x1 = command.Start[0];
            double y1 = command.Start[1];
            double x2 = command.End[0];
            double y2 = command.End[1];

            Polyline polyline = new Polyline(4);
            polyline.AddVertexAt(0, new Point2d(x1, y1), 0, 0, 0);
            polyline.AddVertexAt(1, new Point2d(x2, y1), 0, 0, 0);
            polyline.AddVertexAt(2, new Point2d(x2, y2), 0, 0, 0);
            polyline.AddVertexAt(3, new Point2d(x1, y2), 0, 0, 0);
            polyline.Closed = true;
            return polyline;
        }

        private static Circle CreateCircle(DrawCommand command)
        {
            double radius = command.Radius ?? 0;
            return command.Center != null && radius > 0
                ? new Circle(DrawingTools.ToPoint3d(command.Center), Vector3d.ZAxis, radius)
                : null;
        }

        private static Arc CreateArc(DrawCommand command)
        {
            double radius = command.Radius ?? 0;
            if (command.Center == null || radius <= 0)
            {
                return null;
            }

            double startAngle = command.StartAngle ?? 0;
            double endAngle = command.EndAngle ?? 90;

            return new Arc(
                DrawingTools.ToPoint3d(command.Center),
                radius,
                DegreesToRadians(startAngle),
                DegreesToRadians(endAngle));
        }

        private static DBText CreateText(DrawCommand command)
        {
            if (command.Position == null || string.IsNullOrWhiteSpace(command.Content))
            {
                return null;
            }

            DBText text = new DBText();
            text.SetDatabaseDefaults();
            text.TextString = command.Content;
            text.Position = DrawingTools.ToPoint3d(command.Position);
            text.Height = command.Height.HasValue && command.Height.Value > 0 ? command.Height.Value : 250;
            return text;
        }

        private static AlignedDimension CreateDimension(DrawCommand command)
        {
            if (command.Start == null || command.End == null)
            {
                return null;
            }

            Point3d start = DrawingTools.ToPoint3d(command.Start);
            Point3d end = DrawingTools.ToPoint3d(command.End);
            double offset = command.Offset.HasValue && command.Offset.Value != 0 ? command.Offset.Value : 500;
            Point3d dimLine = new Point3d((start.X + end.X) / 2.0, (start.Y + end.Y) / 2.0 + offset, 0);

            return new AlignedDimension(start, end, dimLine, string.Empty, ObjectId.Null);
        }

        private static BlockReference CreateBlockReference(Transaction transaction, Database database, DrawCommand command)
        {
            if (command.Position == null || string.IsNullOrWhiteSpace(command.Name))
            {
                return null;
            }

            BlockTable blockTable = (BlockTable)transaction.GetObject(database.BlockTableId, OpenMode.ForRead);
            if (!blockTable.Has(command.Name))
            {
                Logger.Warn("Block not found: " + command.Name);
                return null;
            }

            BlockReference reference = new BlockReference(DrawingTools.ToPoint3d(command.Position), blockTable[command.Name]);
            double scale = command.Scale.HasValue && command.Scale.Value > 0 ? command.Scale.Value : 1.0;
            reference.ScaleFactors = new Scale3d(scale);
            reference.Rotation = DegreesToRadians(command.Rotation ?? 0);
            return reference;
        }

        private static bool CreateHatch(
            Transaction transaction,
            BlockTableRecord currentSpace,
            DrawCommand command,
            List<string> createdHandles)
        {
            if (command.Boundary == null || command.Boundary.Length < 3)
            {
                return false;
            }

            Polyline boundary = new Polyline(command.Boundary.Length);
            for (int index = 0; index < command.Boundary.Length; index++)
            {
                boundary.AddVertexAt(index, DrawingTools.ToPoint2d(command.Boundary[index]), 0, 0, 0);
            }

            boundary.Closed = true;
            currentSpace.AppendEntity(boundary);
            transaction.AddNewlyCreatedDBObject(boundary, true);
            if (createdHandles != null)
            {
                createdHandles.Add(boundary.Handle.ToString());
            }

            Hatch hatch = new Hatch();
            hatch.SetDatabaseDefaults();
            hatch.SetHatchPattern(HatchPatternType.PreDefined, string.IsNullOrWhiteSpace(command.Pattern) ? "SOLID" : command.Pattern);
            currentSpace.AppendEntity(hatch);
            transaction.AddNewlyCreatedDBObject(hatch, true);
            if (createdHandles != null)
            {
                createdHandles.Add(hatch.Handle.ToString());
            }
            hatch.AppendLoop(HatchLoopTypes.Outermost, new ObjectIdCollection { boundary.ObjectId });
            hatch.EvaluateHatch(true);

            return true;
        }

        private static bool VerifyEntities(Database database, IReadOnlyList<string> handles, bool expectErased)
        {
            using (Transaction transaction = database.TransactionManager.StartOpenCloseTransaction())
            {
                foreach (string handle in handles)
                {
                    Entity entity = OpenEntityByHandle(database, transaction, handle, OpenMode.ForRead, allowErased: expectErased);
                    bool erased = entity == null || entity.IsErased;
                    if (expectErased != erased)
                    {
                        return false;
                    }
                }

                transaction.Commit();
                return true;
            }
        }

        private static Entity OpenEntityByHandle(
            Database database,
            Transaction transaction,
            string handle,
            OpenMode mode,
            bool allowErased = false)
        {
            long handleValue;
            if (!long.TryParse(handle, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out handleValue))
            {
                return null;
            }

            ObjectId objectId;
            try
            {
                objectId = database.GetObjectId(false, new Handle(handleValue), 0);
            }
            catch
            {
                return null;
            }

            if (objectId.IsNull)
            {
                return null;
            }

            return transaction.GetObject(objectId, mode, allowErased) as Entity;
        }

        private static string StoreRollback(
            Database database,
            List<string> handles,
            Action<Database, Transaction> rollbackAction,
            bool eraseEntitiesOnRollback = true)
        {
            string token = "cadrb_" + Guid.NewGuid().ToString("N");
            Dictionary<string, string> signatures = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            using (Transaction transaction = database.TransactionManager.StartOpenCloseTransaction())
            {
                foreach (string handle in handles)
                {
                    Entity entity = OpenEntityByHandle(database, transaction, handle, OpenMode.ForRead);
                    if (entity == null || entity.IsErased)
                    {
                        throw new InvalidOperationException("Cannot capture rollback state for CAD entity " + handle + ".");
                    }

                    signatures[handle] = EntitySignature(entity);
                }

                transaction.Commit();
            }

            CadRollbackRecord record = new CadRollbackRecord
            {
                DatabaseId = database.FingerprintGuid.ToString(),
                EntityHandles = handles.ToList(),
                EntitySignatures = signatures,
                RollbackAction = rollbackAction,
                EraseEntitiesOnRollback = eraseEntitiesOnRollback
            };
            lock (RollbackSync)
            {
                RollbackRecords[token] = record;
                RollbackOrder.Enqueue(token);
                while (RollbackOrder.Count > MaxRollbackRecords)
                {
                    RollbackRecords.Remove(RollbackOrder.Dequeue());
                }
            }

            return token;
        }

        private static void CleanupFailedCommit(
            Document document,
            IReadOnlyList<string> handles,
            Action<Database, Transaction> rollbackAction)
        {
            using (DocumentLock documentLock = document.LockDocument())
            using (Transaction transaction = document.Database.TransactionManager.StartTransaction())
            {
                foreach (string handle in handles)
                {
                    Entity entity = OpenEntityByHandle(document.Database, transaction, handle, OpenMode.ForWrite);
                    if (entity != null && !entity.IsErased)
                    {
                        entity.Erase();
                    }
                }

                rollbackAction?.Invoke(document.Database, transaction);
                transaction.Commit();
            }

            document.Editor.Regen();
        }

        private static CadRollbackRecord GetRollbackRecord(string rollbackToken)
        {
            if (string.IsNullOrWhiteSpace(rollbackToken))
            {
                throw new ArgumentException("rollback_token is required.", nameof(rollbackToken));
            }

            lock (RollbackSync)
            {
                CadRollbackRecord record;
                if (!RollbackRecords.TryGetValue(rollbackToken, out record))
                {
                    throw new InvalidOperationException("Rollback token is unknown, expired, or already used.");
                }

                return record;
            }
        }

        private static string EntitySignature(Entity entity)
        {
            StringBuilder builder = new StringBuilder();
            builder.Append(entity.GetType().FullName);
            builder.Append('|').Append(entity.Layer ?? string.Empty);
            builder.Append('|').Append(entity.ColorIndex.ToString(CultureInfo.InvariantCulture));
            if (entity is Line line)
            {
                AppendPoint(builder, line.StartPoint);
                AppendPoint(builder, line.EndPoint);
            }
            else if (entity is Polyline polyline)
            {
                builder.Append('|').Append(polyline.Closed ? "1" : "0");
                builder.Append('|').Append(polyline.NumberOfVertices.ToString(CultureInfo.InvariantCulture));
                for (int index = 0; index < polyline.NumberOfVertices; index++)
                {
                    Point2d point = polyline.GetPoint2dAt(index);
                    builder.Append('|').Append(point.X.ToString("R", CultureInfo.InvariantCulture));
                    builder.Append(',').Append(point.Y.ToString("R", CultureInfo.InvariantCulture));
                    builder.Append(',').Append(polyline.GetBulgeAt(index).ToString("R", CultureInfo.InvariantCulture));
                }
            }
            else if (entity is Circle circle)
            {
                AppendPoint(builder, circle.Center);
                builder.Append('|').Append(circle.Radius.ToString("R", CultureInfo.InvariantCulture));
            }
            else if (entity is Arc arc)
            {
                AppendPoint(builder, arc.Center);
                builder.Append('|').Append(arc.Radius.ToString("R", CultureInfo.InvariantCulture));
                builder.Append('|').Append(arc.StartAngle.ToString("R", CultureInfo.InvariantCulture));
                builder.Append('|').Append(arc.EndAngle.ToString("R", CultureInfo.InvariantCulture));
            }
            else if (entity is DBText text)
            {
                AppendPoint(builder, text.Position);
                builder.Append('|').Append(text.Height.ToString("R", CultureInfo.InvariantCulture));
                builder.Append('|').Append(text.TextString ?? string.Empty);
            }
            else if (entity is AlignedDimension dimension)
            {
                AppendPoint(builder, dimension.XLine1Point);
                AppendPoint(builder, dimension.XLine2Point);
                AppendPoint(builder, dimension.DimLinePoint);
                builder.Append('|').Append(dimension.DimensionText ?? string.Empty);
            }
            else if (entity is BlockReference block)
            {
                AppendPoint(builder, block.Position);
                builder.Append('|').Append(block.Rotation.ToString("R", CultureInfo.InvariantCulture));
                builder.Append('|').Append(block.ScaleFactors.X.ToString("R", CultureInfo.InvariantCulture));
                builder.Append(',').Append(block.ScaleFactors.Y.ToString("R", CultureInfo.InvariantCulture));
                builder.Append(',').Append(block.ScaleFactors.Z.ToString("R", CultureInfo.InvariantCulture));
            }
            else if (entity is Hatch hatch)
            {
                builder.Append('|').Append(hatch.PatternName ?? string.Empty);
                builder.Append('|').Append(hatch.NumberOfLoops.ToString(CultureInfo.InvariantCulture));
            }
            else
            {
                try
                {
                    Extents3d extents = entity.GeometricExtents;
                    AppendPoint(builder, extents.MinPoint);
                    AppendPoint(builder, extents.MaxPoint);
                }
                catch
                {
                    builder.Append("|no-extents");
                }
            }

            return builder.ToString();
        }

        private static void AppendPoint(StringBuilder builder, Point3d point)
        {
            builder.Append('|').Append(point.X.ToString("R", CultureInfo.InvariantCulture));
            builder.Append(',').Append(point.Y.ToString("R", CultureInfo.InvariantCulture));
            builder.Append(',').Append(point.Z.ToString("R", CultureInfo.InvariantCulture));
        }

        private sealed class CadRollbackRecord
        {
            public string DatabaseId { get; set; }

            public List<string> EntityHandles { get; set; }

            public Dictionary<string, string> EntitySignatures { get; set; }

            public Action<Database, Transaction> RollbackAction { get; set; }

            public bool EraseEntitiesOnRollback { get; set; }
        }

        private static double DegreesToRadians(double degrees)
        {
            return Math.PI * degrees / 180.0;
        }
    }
}
