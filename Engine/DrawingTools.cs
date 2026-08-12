using Autodesk.AutoCAD.Colors;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

namespace AgentBridge.Engine
{
    internal static class DrawingTools
    {
        public static Point3d ToPoint3d(double[] point)
        {
            return new Point3d(point[0], point[1], point.Length > 2 ? point[2] : 0);
        }

        public static Point2d ToPoint2d(double[] point)
        {
            return new Point2d(point[0], point[1]);
        }

        public static void EnsureLayer(Transaction transaction, Database database, string layerName, int? colorIndex)
        {
            if (string.IsNullOrWhiteSpace(layerName))
            {
                return;
            }

            LayerTable layerTable = (LayerTable)transaction.GetObject(database.LayerTableId, OpenMode.ForRead);
            if (layerTable.Has(layerName))
            {
                return;
            }

            layerTable.UpgradeOpen();
            LayerTableRecord layer = new LayerTableRecord
            {
                Name = layerName,
                Color = Color.FromColorIndex(ColorMethod.ByAci, (short)(colorIndex ?? 7))
            };
            layerTable.Add(layer);
            transaction.AddNewlyCreatedDBObject(layer, true);
        }
    }
}