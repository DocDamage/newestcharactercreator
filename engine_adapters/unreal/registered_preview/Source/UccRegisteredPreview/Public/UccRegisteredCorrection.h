#pragma once

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

namespace UccRegisteredCorrection
{
    struct FVector { float X, Y, Z; };
    struct FRange { std::uint32_t Start, Count; };
    struct FCorner { std::uint32_t Previous, Current, Following, Reserved; };
    struct FOffset { float X, Y, Z, W; };

    struct FTopology
    {
        std::vector<FRange> NeighborRanges;
        std::vector<std::uint32_t> Neighbors;
        std::vector<FCorner> Corners;
        std::vector<FOffset> BindOffsets;
        std::vector<FRange> CornerRanges;
        std::vector<std::uint32_t> CornerIndices;
    };

    // One kernel owns the reusable scratch storage for a single actor.
    class FKernel
    {
    public:
        bool LoadPacket(std::span<const std::uint8_t> Bytes);
        bool Initialize(FTopology Topology, std::vector<std::uint32_t> NativeToSource);
        std::size_t GetNativeVertexCount() const { return NativeToSource.size(); }
        std::size_t GetSourceVertexCount() const { return FirstNative.size(); }

        // Input and output are component-local Unreal positions in centimetres.
        // The two output buffers must be distinct. Neither is written on failure.
        bool Evaluate(std::span<const FVector> RawNativePositionsCm,
                      std::span<FVector> CorrectedNativePositionsCm, std::span<FVector> NativeNormals);

    private:
        struct FContribution { FVector Displacement; float Weight; };

        FTopology Topology;
        std::vector<std::uint32_t> NativeToSource;
        std::vector<std::uint32_t> FirstNative;
        std::vector<FVector> Smoothed, Next, Corrected, FaceNormals, Normals;
        std::vector<FContribution> Contributions;
    };
}
