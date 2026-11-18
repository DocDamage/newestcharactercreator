#include "UccRegisteredCorrection.h"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <limits>
#include <utility>

namespace UccRegisteredCorrection
{
    namespace
    {
        constexpr std::size_t SourceLimit = 13380;
        constexpr std::size_t NativeLimit = 100000;
        constexpr std::size_t CornerLimit = 53512;
        constexpr std::size_t FaceSize = 4;
        constexpr std::uint32_t Missing = std::numeric_limits<std::uint32_t>::max();
        constexpr float DegenerateCorner = 10 * std::numeric_limits<float>::epsilon();
        // Each duplicate is at most 50 micrometres from the source witness.
        constexpr float MaxDuplicateDistanceCm = 0.01f;
        static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);

        FVector operator+(FVector A, FVector B) { return {A.X+B.X, A.Y+B.Y, A.Z+B.Z}; }
        FVector operator-(FVector A, FVector B) { return {A.X-B.X, A.Y-B.Y, A.Z-B.Z}; }
        FVector operator*(FVector A, float S) { return {A.X*S, A.Y*S, A.Z*S}; }
        float Dot(FVector A, FVector B) { return (A.X*B.X+A.Y*B.Y)+A.Z*B.Z; }

        FVector Cross(FVector A, FVector B)
        {
            return {A.Y*B.Z-A.Z*B.Y, A.Z*B.X-A.X*B.Z, A.X*B.Y-A.Y*B.X};
        }

        FVector Unit(FVector A)
        {
            const float Length = std::sqrt(Dot(A, A));
            return Length > 0 ? FVector{A.X/Length, A.Y/Length, A.Z/Length} : FVector{};
        }

        bool Finite(FVector A)
        {
            return std::isfinite(A.X) && std::isfinite(A.Y) && std::isfinite(A.Z);
        }

        // The admitted Unreal basis swaps and negates X/Y. It is its own inverse.
        FVector ConvertBasis(FVector A, float Scale)
        {
            return {-A.Y*Scale, -A.X*Scale, A.Z*Scale};
        }

        bool Covers(std::span<const FRange> Ranges, std::size_t Count)
        {
            std::size_t Start = 0;
            for (const FRange Range : Ranges)
            {
                if (Range.Start != Start || Range.Count == 0 || Range.Count > Count-Start)
                    return false;
                Start += Range.Count;
            }
            return Start == Count;
        }

        bool Dimensions(std::size_t Sources, std::size_t Native, std::size_t Neighbors, std::size_t Corners)
        {
            return Sources > 0 && Sources <= SourceLimit && Native >= Sources && Native <= NativeLimit
                && Neighbors >= Sources && Neighbors <= CornerLimit && Corners >= Sources
                && Corners <= CornerLimit && Corners % FaceSize == 0;
        }

        bool Valid(const FTopology& Topology)
        {
            const std::size_t Sources = Topology.NeighborRanges.size();
            const std::size_t Count = Topology.Corners.size();
            if (Topology.BindOffsets.size() != Count || Topology.CornerIndices.size() != Count
                || Topology.CornerRanges.size() != Sources
                || !Covers(Topology.NeighborRanges, Topology.Neighbors.size()) || !Covers(Topology.CornerRanges, Count))
                return false;
            for (std::uint32_t Vertex : Topology.Neighbors)
                if (Vertex >= Sources)
                    return false;
            for (std::size_t Face = 0; Face < Count; Face += FaceSize)
            {
                for (std::size_t K = 0; K < FaceSize; ++K)
                {
                    const std::size_t Index = Face+K;
                    const FCorner Corner = Topology.Corners[Index];
                    const FOffset Offset = Topology.BindOffsets[Index];
                    if (Corner.Current >= Sources || Corner.Reserved != 0 || Offset.W != 1
                        || !Finite({Offset.X, Offset.Y, Offset.Z})
                        || Corner.Previous != Topology.Corners[Face+(K+3)%FaceSize].Current
                        || Corner.Following != Topology.Corners[Face+(K+1)%FaceSize].Current)
                        return false;
                    for (std::size_t J = 0; J < K; ++J)
                        if (Corner.Current == Topology.Corners[Face+J].Current)
                            return false;
                }
            }
            // Exact ownership and strictly increasing indices reject repeated/skipped corners.
            for (std::size_t Vertex = 0; Vertex < Sources; ++Vertex)
            {
                const FRange Range = Topology.CornerRanges[Vertex];
                for (std::uint32_t J = Range.Start; J < Range.Start+Range.Count; ++J)
                {
                    const std::uint32_t Index = Topology.CornerIndices[J];
                    if (Index >= Count || Topology.Corners[Index].Current != Vertex
                        || (J > Range.Start && Index <= Topology.CornerIndices[J-1]))
                        return false;
                }
            }
            return true;
        }
    }

    bool FKernel::LoadPacket(std::span<const std::uint8_t> Bytes)
    {
        constexpr std::array<std::uint8_t, 8> Magic{'U','C','C','R','C','O','R','1'};
        constexpr std::size_t HeaderBytes = Magic.size()+6*4;
        if (Bytes.size() < HeaderBytes || !std::equal(Magic.begin(), Magic.end(), Bytes.begin()))
            return false;
        std::size_t Cursor = Magic.size();
        const auto Read = [&]()
        {
            const auto Word = std::uint32_t(Bytes[Cursor]) | (std::uint32_t(Bytes[Cursor+1])<<8)
                | (std::uint32_t(Bytes[Cursor+2])<<16) | (std::uint32_t(Bytes[Cursor+3])<<24);
            Cursor += 4;
            return Word;
        };
        const std::size_t Sources = Read();
        const std::size_t Native = Read();
        const std::size_t Neighbors = Read();
        const std::size_t Corners = Read();
        const std::size_t Faces = Read();
        if (Read() != 0 || !Dimensions(Sources, Native, Neighbors, Corners) || Faces != Corners/FaceSize
            || Bytes.size() != HeaderBytes+4*(Native+4*Sources+Neighbors+9*Corners))
            return false;

        FTopology Data;
        std::vector<std::uint32_t> Map(Native);
        Data.NeighborRanges.resize(Sources);
        Data.Neighbors.resize(Neighbors);
        Data.Corners.resize(Corners);
        Data.BindOffsets.resize(Corners);
        Data.CornerRanges.resize(Sources);
        Data.CornerIndices.resize(Corners);
        for (auto& Vertex : Map) Vertex = Read();
        for (auto& Range : Data.NeighborRanges) Range = {Read(), Read()};
        for (auto& Vertex : Data.Neighbors) Vertex = Read();
        for (auto& Corner : Data.Corners) Corner = {Read(), Read(), Read(), Read()};
        const auto ReadFloat = [&]() { return std::bit_cast<float>(Read()); };
        for (auto& Offset : Data.BindOffsets) Offset = {ReadFloat(), ReadFloat(), ReadFloat(), ReadFloat()};
        for (auto& Range : Data.CornerRanges) Range = {Read(), Read()};
        for (auto& Corner : Data.CornerIndices) Corner = Read();
        return Initialize(std::move(Data), std::move(Map));
    }

    bool FKernel::Initialize(FTopology Data, std::vector<std::uint32_t> Map)
    {
        const std::size_t Sources = Data.NeighborRanges.size();
        if (!Dimensions(Sources, Map.size(), Data.Neighbors.size(), Data.Corners.size()) || !Valid(Data))
            return false;
        std::vector<std::uint32_t> Representatives(Sources, Missing);
        for (std::uint32_t Native = 0; Native < Map.size(); ++Native)
        {
            const std::uint32_t Source = Map[Native];
            if (Source >= Sources)
                return false;
            if (Representatives[Source] == Missing)
                Representatives[Source] = Native;
        }
        if (std::find(Representatives.begin(), Representatives.end(), Missing) != Representatives.end())
            return false;

        Topology = std::move(Data);
        NativeToSource = std::move(Map);
        FirstNative = std::move(Representatives);
        Smoothed.resize(Sources);
        Next.resize(Sources);
        Corrected.resize(Sources);
        Normals.resize(Sources);
        Contributions.resize(Topology.Corners.size());
        FaceNormals.resize(Topology.Corners.size()/FaceSize);
        return true;
    }

    bool FKernel::Evaluate(std::span<const FVector> Raw, std::span<FVector> Positions, std::span<FVector> OutputNormals)
    {
        const std::size_t Sources = FirstNative.size();
        if (Sources == 0 || Raw.size() != NativeToSource.size() || Positions.size() != Raw.size()
            || OutputNormals.size() != Raw.size())
            return false;
        for (std::size_t Native = 0; Native < Raw.size(); ++Native)
        {
            if (!Finite(Raw[Native]))
                return false;
            const FVector Delta = Raw[Native]-Raw[FirstNative[NativeToSource[Native]]];
            if (!Finite(Delta) || Dot(Delta, Delta) > MaxDuplicateDistanceCm*MaxDuplicateDistanceCm)
                return false;
        }
        for (std::size_t Vertex = 0; Vertex < Sources; ++Vertex)
            Smoothed[Vertex] = ConvertBasis(Raw[FirstNative[Vertex]], .01f);

        // Jacobi smoothing uses the preceding complete surface on each iteration.
        for (int Pass = 0; Pass < 5; ++Pass)
        {
            for (std::size_t Vertex = 0; Vertex < Sources; ++Vertex)
            {
                const FVector Center = Smoothed[Vertex];
                const FRange Range = Topology.NeighborRanges[Vertex];
                FVector Sum{};
                for (std::uint32_t J = Range.Start; J < Range.Start+Range.Count; ++J)
                    Sum = Sum+(Smoothed[Topology.Neighbors[J]]-Center);
                Next[Vertex] = Center+Sum*(.5f/static_cast<float>(Range.Count));
            }
            Smoothed.swap(Next);
        }
        for (std::size_t Index = 0; Index < Topology.Corners.size(); ++Index)
        {
            const FCorner K = Topology.Corners[Index];
            const FVector Left = Unit(Smoothed[K.Previous]-Smoothed[K.Current]);
            const FVector Right = Unit(Smoothed[K.Current]-Smoothed[K.Following]);
            const FVector Difference = Left-Right;
            if (std::abs(Difference.X) <= DegenerateCorner && std::abs(Difference.Y) <= DegenerateCorner
                && std::abs(Difference.Z) <= DegenerateCorner)
            {
                Contributions[Index] = {};
                continue;
            }
            const FVector Normal = Unit(Cross(Left, Right));
            const FVector Axis = Unit(Left+Right);
            const FVector Other = Cross(Normal, Axis);
            const FOffset Offset = Topology.BindOffsets[Index];
            Contributions[Index] = {
                Axis*Offset.X+Other*Offset.Y+Normal*Offset.Z,
                std::acos(std::clamp(Dot(Left, Right), -1.f, 1.f))
            };
        }
        for (std::size_t Vertex = 0; Vertex < Sources; ++Vertex)
        {
            const FRange Range = Topology.CornerRanges[Vertex];
            float Total = 0;
            for (std::uint32_t J = Range.Start; J < Range.Start+Range.Count; ++J)
                Total += Contributions[Topology.CornerIndices[J]].Weight;
            FVector Position = Smoothed[Vertex];
            if (Total > 0)
            {
                for (std::uint32_t J = Range.Start; J < Range.Start+Range.Count; ++J)
                {
                    const FContribution Item = Contributions[Topology.CornerIndices[J]];
                    Position = Position+Item.Displacement*(Item.Weight/Total);
                }
            }
            if (!Finite(Position) || !Finite(ConvertBasis(Position, 100.f)))
                return false;
            Corrected[Vertex] = Position;
        }
        for (std::size_t Face = 0; Face < FaceNormals.size(); ++Face)
        {
            const auto Position = [&](std::size_t K)
            {
                return Corrected[Topology.Corners[Face*FaceSize+K].Current];
            };
            const FVector A = Position(1)-Position(0);
            const FVector B = Position(2)-Position(0);
            const FVector C = Position(3)-Position(0);
            const FVector Normal = Unit(Cross(A, B)+Cross(B, C));
            if (!Finite(Normal) || Dot(Normal, Normal) == 0)
                return false;
            FaceNormals[Face] = Normal;
        }
        for (std::size_t Vertex = 0; Vertex < Sources; ++Vertex)
        {
            const FRange Range = Topology.CornerRanges[Vertex];
            FVector Weighted{};
            for (std::uint32_t J = Range.Start; J < Range.Start+Range.Count; ++J)
            {
                const std::uint32_t Index = Topology.CornerIndices[J];
                const FCorner K = Topology.Corners[Index];
                const FVector A = Unit(Corrected[K.Previous]-Corrected[Vertex]);
                const FVector B = Unit(Corrected[K.Following]-Corrected[Vertex]);
                if (Dot(A, A) == 0 || Dot(B, B) == 0)
                    return false;
                const FVector AB = Cross(A, B);
                const float Angle = std::atan2(std::sqrt(Dot(AB, AB)), Dot(A, B));
                Weighted = Weighted+FaceNormals[Index/FaceSize]*Angle;
            }
            const FVector Normal = Unit(Weighted);
            if (!Finite(Normal) || Dot(Normal, Normal) == 0)
                return false;
            Normals[Vertex] = Normal;
        }
        for (std::size_t Native = 0; Native < Raw.size(); ++Native)
        {
            const std::uint32_t Vertex = NativeToSource[Native];
            Positions[Native] = ConvertBasis(Corrected[Vertex], 100.f);
            OutputNormals[Native] = ConvertBasis(Normals[Vertex], 1.f);
        }
        return true;
    }
}
