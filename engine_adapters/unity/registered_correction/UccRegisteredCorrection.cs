using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.Rendering;

namespace Ucc.UnityAdapter
{
    [Serializable]
    public struct UccCorrectionTopologyAsset
    {
        public string name;
        public TextAsset bytes;
        public string sha256;
    }

    // The caller owns the admitted native skin and draw buffers. This pass owns
    // only its topology and intermediate buffers and writes corrected XYZ.
    public sealed class UccRegisteredCorrection : IDisposable
    {
        const int SourceCount = 13380;
        const int CornerCount = 53512;
        const int NativeStride = 40;
        const int Width = 64;

        [StructLayout(LayoutKind.Sequential)]
        struct Range
        {
            public int Start;
            public int Count;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct Corner
        {
            public int Previous;
            public int Vertex;
            public int Next;
            public int Reserved;
        }

        readonly List<ComputeBuffer> owned = new List<ComputeBuffer>();
        readonly ComputeShader shader;
        readonly int nativeCount, gather, smooth, corners, combine, scatter;
        readonly ComputeBuffer firstNative, nativeSource, neighborRanges, neighbors;
        readonly ComputeBuffer sourceCorners, bindOffsets, cornerRanges, cornerOrder;
        readonly ComputeBuffer pointsA, pointsB, contributions, corrected;
        bool disposed;

        public UccRegisteredCorrection(ComputeShader shader, int[] nativeToSource,
                                       UccCorrectionTopologyAsset[] resources)
        {
            if (shader == null || nativeToSource == null || nativeToSource.Length < SourceCount
                || nativeToSource.Length > 200000 || resources == null || resources.Length != 6)
                throw new InvalidDataException("Incomplete admitted Unity corrective inputs");

            this.shader = shader;
            nativeCount = nativeToSource.Length;
            var first = new int[SourceCount];
            for (int id = 0; id < first.Length; ++id)
                first[id] = -1;
            for (int native = 0; native < nativeCount; ++native)
            {
                int source = nativeToSource[native];
                Vertex(source);
                if (first[source] < 0)
                    first[source] = native;
            }
            foreach (int native in first)
                if (native < 0)
                    throw new InvalidDataException("Unity native mapping omits a corrective source vertex");

            var byName = new Dictionary<string, UccCorrectionTopologyAsset>(StringComparer.Ordinal);
            foreach (var resource in resources)
            {
                if (String.IsNullOrEmpty(resource.name) || byName.ContainsKey(resource.name))
                    throw new InvalidDataException("Corrective topology inputs must have distinct exact names");
                byName.Add(resource.name, resource);
            }

            Range[] neighborTable = Read(byName, "neighbor_ranges.u32", SourceCount, 8,
                input => new Range { Start = input.ReadInt32(), Count = input.ReadInt32() });
            int[] neighborIds = Read(byName, "neighbors.u32", CornerCount, 4, input => input.ReadInt32());
            Corner[] cornerTable = Read(byName, "corners.u32", CornerCount, 16, input => new Corner
            {
                Previous = input.ReadInt32(), Vertex = input.ReadInt32(),
                Next = input.ReadInt32(), Reserved = input.ReadInt32()
            });
            Vector4[] offsetTable = Read(byName, "offsets_vec4.f32", CornerCount, 16, input =>
                new Vector4(input.ReadSingle(), input.ReadSingle(), input.ReadSingle(), input.ReadSingle()));
            Range[] cornerTableRanges = Read(byName, "corner_ranges.u32", SourceCount, 8,
                input => new Range { Start = input.ReadInt32(), Count = input.ReadInt32() });
            int[] cornerIds = Read(byName, "corner_indices.u32", CornerCount, 4, input => input.ReadInt32());
            CheckTopology(neighborTable, neighborIds, cornerTable, offsetTable, cornerTableRanges, cornerIds);

            gather = shader.FindKernel("Gather");
            smooth = shader.FindKernel("Smooth");
            corners = shader.FindKernel("Corners");
            combine = shader.FindKernel("Combine");
            scatter = shader.FindKernel("Scatter");
            try
            {
                firstNative = Make(first, 4);
                nativeSource = Make(nativeToSource, 4);
                neighborRanges = Make(neighborTable, 8);
                neighbors = Make(neighborIds, 4);
                sourceCorners = Make(cornerTable, 16);
                bindOffsets = Make(offsetTable, 16);
                cornerRanges = Make(cornerTableRanges, 8);
                cornerOrder = Make(cornerIds, 4);
                pointsA = Allocate(SourceCount, 16);
                pointsB = Allocate(SourceCount, 16);
                contributions = Allocate(CornerCount, 16);
                corrected = Allocate(SourceCount, 16);
            }
            catch
            {
                Dispose();
                throw;
            }
        }

        static T[] Read<T>(Dictionary<string, UccCorrectionTopologyAsset> resources,
                           string name, int count, int width, Func<BinaryReader, T> item)
        {
            if (!resources.TryGetValue(name, out var entry) || entry.bytes == null
                || entry.bytes.dataSize != count * width)
                throw new InvalidDataException("Missing or incorrectly sized corrective topology input: " + name);
            byte[] raw = entry.bytes.bytes;
            if (raw.Length != count * width || UccNativeMeshIdentity.Hash(raw) != entry.sha256)
                throw new InvalidDataException("Corrective topology SHA-256 changed: " + name);
            var data = new T[count];
            using (var input = new BinaryReader(new MemoryStream(raw, false)))
                for (int i = 0; i < count; ++i)
                    data[i] = item(input);
            return data;
        }

        static void Vertex(int vertex)
        {
            if (vertex < 0 || vertex >= SourceCount)
                throw new InvalidDataException("Corrective topology contains a non-source vertex");
        }

        static void Ranges(Range[] ranges)
        {
            int cursor = 0;
            foreach (var range in ranges)
            {
                if (range.Start != cursor || range.Count < 1 || range.Count > 32
                    || range.Count > CornerCount - cursor)
                    throw new InvalidDataException("Incorrect or unbounded corrective topology ranges");
                cursor += range.Count;
            }
            if (cursor != CornerCount)
                throw new InvalidDataException("Corrective topology ranges omit admitted indices");
        }

        static void CheckTopology(Range[] neighborRanges, int[] neighbors, Corner[] corners,
                                  Vector4[] offsets, Range[] cornerRanges, int[] cornerOrder)
        {
            Ranges(neighborRanges);
            Ranges(cornerRanges);
            var seen = new bool[CornerCount];
            for (int vertex = 0; vertex < SourceCount; ++vertex)
            {
                var neighborRange = neighborRanges[vertex];
                for (int i = neighborRange.Start; i < neighborRange.Start + neighborRange.Count; ++i)
                {
                    Vertex(neighbors[i]);
                    if (neighbors[i] == vertex)
                        throw new InvalidDataException("A corrective vertex cannot neighbor itself");
                }
                var cornerRange = cornerRanges[vertex];
                for (int i = cornerRange.Start; i < cornerRange.Start + cornerRange.Count; ++i)
                {
                    int index = cornerOrder[i];
                    if (index < 0 || index >= CornerCount || seen[index] || corners[index].Vertex != vertex)
                        throw new InvalidDataException("Incorrect ordered corrective corner identity");
                    seen[index] = true;
                    var corner = corners[index];
                    Vertex(corner.Previous);
                    Vertex(corner.Next);
                    if (corner.Previous == vertex || corner.Next == vertex || corner.Reserved != 0)
                        throw new InvalidDataException("Invalid corrective corner geometry");

                    var offset = offsets[index];
                    if (!Finite(offset.x) || !Finite(offset.y) || !Finite(offset.z) || offset.w != 1f)
                        throw new InvalidDataException("Nonfinite or malformed corrective bind offset");
                }
            }
        }

        static bool Finite(float value) => !Single.IsNaN(value) && !Single.IsInfinity(value);

        ComputeBuffer Allocate(int count, int stride)
        {
            var buffer = new ComputeBuffer(count, stride);
            owned.Add(buffer);
            return buffer;
        }

        ComputeBuffer Make<T>(T[] data, int stride) where T : struct
        {
            var buffer = Allocate(data.Length, stride);
            buffer.SetData(data);
            return buffer;
        }

        // Record after the caller's native -> owned copy and before its normal
        // pass. Keep this adapter alive while the recorded command can execute.
        public void Record(CommandBuffer commands, GraphicsBuffer nativeSkin, GraphicsBuffer ownedDraw)
        {
            if (disposed)
                throw new ObjectDisposedException(nameof(UccRegisteredCorrection));
            if (commands == null || nativeSkin == null || ownedDraw == null || nativeSkin == ownedDraw
                || nativeSkin.count != nativeCount || ownedDraw.count != nativeCount
                || nativeSkin.stride != NativeStride || ownedDraw.stride != NativeStride)
                throw new InvalidDataException("Corrective pass requires two distinct verified native GPU buffers");

            commands.SetComputeIntParam(shader, "_SourceCount", SourceCount);
            commands.SetComputeIntParam(shader, "_CornerCount", CornerCount);
            commands.SetComputeIntParam(shader, "_NativeCount", nativeCount);
            commands.SetComputeBufferParam(shader, gather, "_Native", nativeSkin);
            commands.SetComputeBufferParam(shader, gather, "_FirstNative", firstNative);
            commands.SetComputeBufferParam(shader, gather, "_SmoothOutput", pointsA);
            Dispatch(commands, gather, SourceCount);

            commands.SetComputeBufferParam(shader, smooth, "_NeighborRanges", neighborRanges);
            commands.SetComputeBufferParam(shader, smooth, "_Neighbors", neighbors);
            ComputeBuffer input = pointsA;
            ComputeBuffer output = pointsB;
            for (int step = 0; step < 5; ++step)
            {
                commands.SetComputeBufferParam(shader, smooth, "_SmoothInput", input);
                commands.SetComputeBufferParam(shader, smooth, "_SmoothOutput", output);
                Dispatch(commands, smooth, SourceCount);
                (input, output) = (output, input);
            }

            commands.SetComputeBufferParam(shader, corners, "_SmoothInput", input);
            commands.SetComputeBufferParam(shader, corners, "_Corners", sourceCorners);
            commands.SetComputeBufferParam(shader, corners, "_BindOffsets", bindOffsets);
            commands.SetComputeBufferParam(shader, corners, "_ContributionsOut", contributions);
            Dispatch(commands, corners, CornerCount);

            commands.SetComputeBufferParam(shader, combine, "_SmoothInput", input);
            commands.SetComputeBufferParam(shader, combine, "_CornerRanges", cornerRanges);
            commands.SetComputeBufferParam(shader, combine, "_CornerOrder", cornerOrder);
            commands.SetComputeBufferParam(shader, combine, "_ContributionsIn", contributions);
            commands.SetComputeBufferParam(shader, combine, "_CorrectedOut", corrected);
            Dispatch(commands, combine, SourceCount);

            commands.SetComputeBufferParam(shader, scatter, "_CorrectedIn", corrected);
            commands.SetComputeBufferParam(shader, scatter, "_NativeSource", nativeSource);
            commands.SetComputeBufferParam(shader, scatter, "_Owned", ownedDraw);
            Dispatch(commands, scatter, nativeCount);
        }

        void Dispatch(CommandBuffer commands, int kernel, int count)
        {
            commands.DispatchCompute(shader, kernel, (count + Width - 1) / Width, 1, 1);
        }

        public void Dispose()
        {
            if (disposed)
                return;
            disposed = true;
            foreach (var buffer in owned)
                buffer.Release();
            owned.Clear();
        }
    }
}
