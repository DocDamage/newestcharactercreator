#include "UccNativeObservationLibrary.h"
#include "Engine/SkeletalMesh.h"
#include "UObject/Package.h"
#include "Materials/MaterialInterface.h"
#include "Animation/MorphTarget.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "ReferenceSkeleton.h"
#include "Misc/Base64.h"
#include "Misc/EngineVersion.h"
#include "Modules/ModuleManager.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#if !PLATFORM_WINDOWS || !PLATFORM_LITTLE_ENDIAN
#error This private observation profile is explicitly Windows little-endian only.
#endif
namespace
{
constexpr uint32 MaxVertices = 200000;
constexpr uint32 MaxIndices = 1200000;
constexpr uint32 MaxBones = 1024;
constexpr uint32 MaxMorphs = 256;
constexpr uint32 MaxMorphDeltas = 500000;
FString FailureText(const TCHAR* Reason)
{
    return FString::Printf(TEXT("{\"schema_version\":2,\"policy\":\"UCC_PRIVATE_UNREAL_CONST_OBSERVATION_V2\",\"engine_version\":\"\",\"observer_module\":\"\",\"status\":\"REJECTED\",\"reason\":\"%s\",\"native_data_observed\":false,\"source_parity_verified\":false,\"runtime_gpu_verified\":false,\"asset_modified_or_saved\":false,\"readback\":{}}"), Reason);
}
FString Finish(const TSharedRef<FJsonObject>& Root)
{
    FString Text;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
    if (!FJsonSerializer::Serialize(Root, Writer)) return FailureText(TEXT("SERIALIZATION_FAILED"));
    if (Text.Len() > 128 * 1024 * 1024) return FailureText(TEXT("SERIALIZED_OUTPUT_LIMIT"));
    return Text;
}
void PutBytes(TArray<uint8>& Out, const void* Data, uint32 Bytes)
{
    Out.Append(static_cast<const uint8*>(Data), Bytes);
}
void PutU32(TArray<uint8>& Out, uint32 Value) { PutBytes(Out, &Value, sizeof(Value)); }
void PutU16(TArray<uint8>& Out, uint16 Value) { PutBytes(Out, &Value, sizeof(Value)); }
void PutV3(TArray<uint8>& Out, const FVector3f& Value)
{
    static_assert(sizeof(FVector3f) == 12);
    PutBytes(Out, &Value, 12);
}
TSharedRef<FJsonObject> Buffer(const TArray<uint8>& Bytes, const TCHAR* Encoding, uint32 Count)
{
    TSharedRef<FJsonObject> Value = MakeShared<FJsonObject>();
    Value->SetStringField(TEXT("encoding"), Encoding);
    Value->SetNumberField(TEXT("count"), Count);
    Value->SetNumberField(TEXT("bytes"), Bytes.Num());
    Value->SetStringField(TEXT("base64"), FBase64::Encode(Bytes));
    return Value;
}
}
FString UUccNativeObservationLibrary::ObserveSkeletalMesh(USkeletalMesh* Input)
{
    TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetNumberField(TEXT("schema_version"), 2);
    Root->SetStringField(TEXT("policy"), TEXT("UCC_PRIVATE_UNREAL_CONST_OBSERVATION_V2"));
    Root->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());
    Root->SetStringField(TEXT("observer_module"),
        FModuleManager::Get().GetModuleFilename(TEXT("UccNativeObservation")));
    Root->SetStringField(TEXT("status"), TEXT("REJECTED"));
    Root->SetStringField(TEXT("reason"), TEXT("NULL_MESH"));
    Root->SetBoolField(TEXT("native_data_observed"), false);
    Root->SetBoolField(TEXT("source_parity_verified"), false);
    Root->SetBoolField(TEXT("runtime_gpu_verified"), false);
    Root->SetBoolField(TEXT("asset_modified_or_saved"), false);
    Root->SetObjectField(TEXT("readback"), MakeShared<FJsonObject>());
    if (!Input) return Finish(Root);
    auto Reject = [&Root](const TCHAR* Reason) { Root->SetStringField(TEXT("reason"), Reason); return Finish(Root); };
    if (!IsInGameThread()) return Reject(TEXT("GAME_THREAD_REQUIRED"));
    const USkeletalMesh* Mesh = Input;
    if (Mesh->IsCompiling()) return Reject(TEXT("MESH_COMPILATION_INCOMPLETE"));
    const FSkeletalMeshRenderData* Render = Mesh->GetResourceForRendering();
    if (!Render || Render->LODRenderData.Num() < 1) return Reject(TEXT("MISSING_NATIVE_LOD0"));
    const FSkeletalMeshLODRenderData& LOD = Render->LODRenderData[0];
    const uint32 NumVertices = LOD.GetNumVertices();
    const auto& Positions = LOD.StaticVertexBuffers.PositionVertexBuffer;
    const auto& Static = LOD.StaticVertexBuffers.StaticMeshVertexBuffer;
    const auto& Weights = LOD.SkinWeightVertexBuffer;
    if (!NumVertices || NumVertices > MaxVertices || Weights.GetNumVertices() != NumVertices
        || Positions.GetNumVertices() != NumVertices || Static.GetNumVertices() != NumVertices || !Static.GetNumTexCoords()
        || !Positions.GetVertexData() || !Static.GetTangentData() || !Static.GetTexCoordData()
        || !Weights.GetDataVertexBuffer()->GetWeightData()) return Reject(TEXT("MISSING_OR_UNBOUNDED_NATIVE_CPU_DATA"));
    if (Weights.GetVariableBonesPerVertex() && !Weights.GetLookupVertexBuffer()->GetLookupData())
        return Reject(TEXT("MISSING_NATIVE_INFLUENCE_LOOKUP"));
    const FReferenceSkeleton& Skeleton = Mesh->GetRefSkeleton();
    if (Skeleton.GetNum() < 1 || Skeleton.GetNum() > static_cast<int32>(MaxBones)) return Reject(TEXT("UNBOUNDED_NATIVE_SKELETON"));
    if (!LOD.MultiSizeIndexContainer.IsIndexBufferValid() || LOD.MultiSizeIndexContainer.GetIndexBuffer()->Num() < 3 || LOD.MultiSizeIndexContainer.GetIndexBuffer()->Num() > static_cast<int32>(MaxIndices)
        || LOD.RenderSections.Num() > 1024 || Mesh->GetMaterials().Num() > 64
        || LOD.GetUnifiedBoneMap().Num() > static_cast<int32>(MaxBones)) return Reject(TEXT("UNBOUNDED_NATIVE_COLLECTION"));
    TArray<uint32> IndexValues;
    LOD.MultiSizeIndexContainer.GetIndexBuffer(IndexValues);
    if (IndexValues.Num() < 3 || IndexValues.Num() > static_cast<int32>(MaxIndices) || IndexValues.Num() % 3)
        return Reject(TEXT("INVALID_NATIVE_TRIANGLE_BUFFER"));
    TArray<uint8> P, N, UV, Indices, InfluenceRows, InfluenceCounts, BindMatrices;
    for (uint32 Index : IndexValues)
    {
        if (Index >= NumVertices) return Reject(TEXT("NATIVE_TRIANGLE_INDEX_OUT_OF_RANGE"));
        PutU32(Indices, Index);
    }
    uint32 InfluenceCount = 0;
    for (uint32 Vertex = 0; Vertex < NumVertices; ++Vertex)
    {
        const FVector3f& Position = Positions.VertexPosition(Vertex);
        const FVector4f Normal = Static.VertexTangentZ(Vertex);
        const FVector2f Texcoord = Static.GetVertexUV(Vertex, 0);
        if (!FMath::IsFinite(Position.X) || !FMath::IsFinite(Position.Y) || !FMath::IsFinite(Position.Z)
            || !FMath::IsFinite(Normal.X) || !FMath::IsFinite(Normal.Y) || !FMath::IsFinite(Normal.Z)
            || !FMath::IsFinite(Texcoord.X) || !FMath::IsFinite(Texcoord.Y)) return Reject(TEXT("NONFINITE_NATIVE_VERTEX"));
        PutV3(P, Position);
        PutV3(N, FVector3f(Normal.X, Normal.Y, Normal.Z));
        PutBytes(UV, &Texcoord, sizeof(Texcoord));
        uint32 Offset = 0, Count = 0;
        Weights.GetVertexInfluenceOffsetCount(Vertex, Offset, Count);
        if (!Count || Count > 64) return Reject(TEXT("UNBOUNDED_NATIVE_INFLUENCES"));
        const TArray<FBoneIndexType>* SectionBones = nullptr;
        const TConstArrayView<FBoneIndexType> Unified = LOD.GetUnifiedBoneMap();
        if (!LOD.HasUnifiedBoneMap())
        {
            uint32 Matches = 0;
            for (const FSkelMeshRenderSection& Section : LOD.RenderSections)
                if (Vertex >= Section.BaseVertexIndex && Vertex - Section.BaseVertexIndex < Section.NumVertices)
                { SectionBones = &Section.BoneMap; ++Matches; }
            if (Matches != 1) return Reject(TEXT("AMBIGUOUS_NATIVE_SECTION_BONE_MAP"));
        }
        uint32 Positive = 0;
        for (uint32 Influence = 0; Influence < Count; ++Influence)
        {
            const uint16 Weight = Weights.GetBoneWeight(Vertex, Influence);
            if (!Weight) continue;
            const uint32 Mapped = Weights.GetBoneIndex(Vertex, Influence);
            uint32 Bone = 0;
            if (LOD.HasUnifiedBoneMap())
            {
                if (Mapped >= static_cast<uint32>(Unified.Num())) return Reject(TEXT("INVALID_UNIFIED_NATIVE_BONE"));
                Bone = Unified[Mapped];
            }
            else
            {
                if (!SectionBones || Mapped >= static_cast<uint32>(SectionBones->Num())) return Reject(TEXT("INVALID_SECTION_NATIVE_BONE"));
                Bone = (*SectionBones)[Mapped];
            }
            if (Bone >= static_cast<uint32>(Skeleton.GetNum())) return Reject(TEXT("NATIVE_BONE_OUT_OF_RANGE"));
            if (InfluenceCount >= 1000000) return Reject(TEXT("UNBOUNDED_NATIVE_POSITIVE_INFLUENCES"));
            PutU32(InfluenceRows, Vertex); PutU32(InfluenceRows, Bone); PutU16(InfluenceRows, Weight);
            ++Positive; ++InfluenceCount;
        }
        if (!Positive) return Reject(TEXT("NATIVE_VERTEX_HAS_NO_POSITIVE_WEIGHT"));
        PutU32(InfluenceCounts, Positive);
    }
    TArray<TSharedPtr<FJsonValue>> BoneRows;
    const auto& Infos = Skeleton.GetRefBoneInfo();
    const auto& Poses = Skeleton.GetRefBonePose();
    const auto& InverseBind = Mesh->GetRefBasesInvMatrix();
    if (Infos.Num() != Poses.Num() || InverseBind.Num() != Infos.Num()) return Reject(TEXT("INCOMPLETE_NATIVE_BIND"));
    for (int32 Bone = 0; Bone < Infos.Num(); ++Bone)
    {
        TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("name"), Infos[Bone].Name.ToString());
        Row->SetNumberField(TEXT("parent"), Infos[Bone].ParentIndex);
        TArray<TSharedPtr<FJsonValue>> LocalTRS;
        const auto Rotation = Poses[Bone].GetRotation();
        const auto Translation = Poses[Bone].GetTranslation();
        const auto Scale = Poses[Bone].GetScale3D();
        for (double Value : {Rotation.X, Rotation.Y, Rotation.Z, Rotation.W,
            Translation.X, Translation.Y, Translation.Z, Scale.X, Scale.Y, Scale.Z})
        {
            if (!FMath::IsFinite(Value)) return Reject(TEXT("NONFINITE_NATIVE_BONE"));
            LocalTRS.Add(MakeShared<FJsonValueNumber>(Value));
        }
        Row->SetArrayField(TEXT("local_trs_float64_quaternion_xyzw_translation_scale"), LocalTRS);
        BoneRows.Add(MakeShared<FJsonValueObject>(Row));
        for (uint32 I = 0; I < 4; ++I) for (uint32 J = 0; J < 4; ++J)
        {
            const float Value = InverseBind[Bone].M[I][J];
            if (!FMath::IsFinite(Value)) return Reject(TEXT("NONFINITE_NATIVE_INVERSE_BIND"));
            PutBytes(BindMatrices, &Value, sizeof(Value));
        }
    }
    const auto& Morphs = Mesh->GetMorphTargets();
    if (Morphs.Num() > static_cast<int32>(MaxMorphs)) return Reject(TEXT("UNBOUNDED_NATIVE_MORPHS"));
    TArray<TSharedPtr<FJsonValue>> MorphRows;
    uint32 AllDeltas = 0;
    for (const auto& Morph : Morphs)
    {
        if (!Morph) return Reject(TEXT("MISSING_NATIVE_MORPH"));
        const TConstArrayView<FMorphTargetDelta> Deltas = Morph->GetMorphTargetDeltas(0);
        if (Deltas.Num() > static_cast<int32>(MaxMorphDeltas - AllDeltas)) return Reject(TEXT("UNBOUNDED_NATIVE_MORPH_DELTAS"));
        AllDeltas += Deltas.Num();
        TArray<uint8> Packed;
        for (const FMorphTargetDelta& Delta : Deltas)
        {
            if (Delta.SourceIdx >= NumVertices) return Reject(TEXT("NATIVE_MORPH_INDEX_OUT_OF_RANGE"));
            if (!FMath::IsFinite(Delta.PositionDelta.X) || !FMath::IsFinite(Delta.PositionDelta.Y)
                || !FMath::IsFinite(Delta.PositionDelta.Z) || !FMath::IsFinite(Delta.TangentZDelta.X)
                || !FMath::IsFinite(Delta.TangentZDelta.Y) || !FMath::IsFinite(Delta.TangentZDelta.Z))
                return Reject(TEXT("NONFINITE_NATIVE_MORPH"));
            PutU32(Packed, Delta.SourceIdx); PutV3(Packed, Delta.PositionDelta); PutV3(Packed, Delta.TangentZDelta);
        }
        TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("name"), Morph->GetName());
        Row->SetObjectField(TEXT("deltas"), Buffer(Packed, TEXT("uint32_native_index_float32x3_position_float32x3_tangent_le"), Deltas.Num()));
        MorphRows.Add(MakeShared<FJsonValueObject>(Row));
    }
    TSharedRef<FJsonObject> Readback = MakeShared<FJsonObject>();
    Readback->SetStringField(TEXT("mesh_package"), Mesh->GetOutermost()->GetName());
    Readback->SetStringField(TEXT("unit"), TEXT("native_unreal_centimeter"));
    Readback->SetObjectField(TEXT("positions"), Buffer(P, TEXT("float32x3_le"), NumVertices));
    Readback->SetObjectField(TEXT("normals"), Buffer(N, TEXT("float32x3_le"), NumVertices));
    Readback->SetObjectField(TEXT("uv0"), Buffer(UV, TEXT("float32x2_le"), NumVertices));
    Readback->SetObjectField(TEXT("triangle_indices"), Buffer(Indices, TEXT("uint32_le"), IndexValues.Num()));
    Readback->SetObjectField(TEXT("positive_influence_counts"), Buffer(InfluenceCounts, TEXT("uint32_le"), NumVertices));
    Readback->SetObjectField(TEXT("positive_influences"), Buffer(InfluenceRows, TEXT("uint32_vertex_uint32_bone_uint16_apiweight_le"), InfluenceCount));
    Readback->SetNumberField(TEXT("native_weight_storage_bytes"), Weights.GetBoneWeightByteSize());
    Readback->SetNumberField(TEXT("native_bone_index_storage_bytes"), Weights.GetBoneIndexByteSize());
    Readback->SetBoolField(TEXT("native_variable_influences"), Weights.GetVariableBonesPerVertex());
    Readback->SetBoolField(TEXT("native_unified_bone_map"), LOD.HasUnifiedBoneMap());
    Readback->SetStringField(TEXT("api_weight_normalization"), TEXT("uint16_div65535; stored8bit_expands257_per_engine_accessor"));
    Readback->SetObjectField(TEXT("inverse_bind_matrices"), Buffer(BindMatrices, TEXT("float32x16_rowmajor_le"), Infos.Num()));
    Readback->SetArrayField(TEXT("bones"), BoneRows);
    Readback->SetArrayField(TEXT("morphs"), MorphRows);
    Readback->SetStringField(TEXT("mesh_object"), Mesh->GetPathName());
    Readback->SetBoolField(TEXT("native_uv_storage_full_precision"), Static.GetUseFullPrecisionUVs());
    Readback->SetBoolField(TEXT("native_high_precision_tangent_basis"), Static.GetUseHighPrecisionTangentBasis());
    Readback->SetNumberField(TEXT("native_max_bone_influences"), Weights.GetMaxBoneInfluences());
    Readback->SetNumberField(TEXT("native_constant_influences_stride"), Weights.GetConstantInfluencesVertexStride());
    Readback->SetNumberField(TEXT("native_constant_influences_bone_weights_offset"), Weights.GetConstantInfluencesBoneWeightsOffset());
    TArray<uint8> RawWeights, RawLookup;
    const uint32 WeightBytes = Weights.GetDataVertexBuffer()->GetVertexDataSize();
    const uint32 LookupBytes = Weights.GetLookupVertexBuffer()->GetVertexDataSize();
    if (WeightBytes > 16 * 1024 * 1024 || LookupBytes > MaxVertices * 4)
        return Reject(TEXT("UNBOUNDED_NATIVE_RAW_WEIGHT_STORAGE"));
    if (WeightBytes) PutBytes(RawWeights, Weights.GetDataVertexBuffer()->GetWeightData(), WeightBytes);
    if (LookupBytes)
    {
        if (!Weights.GetLookupVertexBuffer()->GetLookupData()) return Reject(TEXT("MISSING_NATIVE_RAW_LOOKUP"));
        PutBytes(RawLookup, Weights.GetLookupVertexBuffer()->GetLookupData(), LookupBytes);
    }
    Readback->SetObjectField(TEXT("native_weight_data"), Buffer(RawWeights, TEXT("uint8_native_skin_weight_storage"), WeightBytes));
    Readback->SetObjectField(TEXT("native_weight_lookup"), Buffer(RawLookup, TEXT("uint8_native_skin_weight_lookup_storage"), LookupBytes));
    TArray<TSharedPtr<FJsonValue>> UnifiedRows, SectionRows, MaterialRows;
    for (const FBoneIndexType Bone : LOD.GetUnifiedBoneMap()) UnifiedRows.Add(MakeShared<FJsonValueNumber>(Bone));
    Readback->SetArrayField(TEXT("unified_bone_map"), UnifiedRows);
    for (const FSkelMeshRenderSection& Section : LOD.RenderSections)
    {
        if (Section.BoneMap.Num() > static_cast<int32>(MaxBones)) return Reject(TEXT("UNBOUNDED_NATIVE_SECTION_BONE_MAP"));
        TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
        Row->SetNumberField(TEXT("material_index"), Section.MaterialIndex);
        Row->SetNumberField(TEXT("base_index"), Section.BaseIndex);
        Row->SetNumberField(TEXT("num_triangles"), Section.NumTriangles);
        Row->SetNumberField(TEXT("base_vertex_index"), Section.BaseVertexIndex);
        Row->SetNumberField(TEXT("num_vertices"), Section.NumVertices);
        Row->SetNumberField(TEXT("max_bone_influences"), Section.MaxBoneInfluences);
        Row->SetBoolField(TEXT("has_unified_bone_map"), Section.HasUnifiedBoneMap());
        TArray<TSharedPtr<FJsonValue>> Map;
        for (const FBoneIndexType Bone : Section.BoneMap) Map.Add(MakeShared<FJsonValueNumber>(Bone));
        Row->SetArrayField(TEXT("bone_map"), Map);
        SectionRows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Readback->SetArrayField(TEXT("sections"), SectionRows);
    for (const FSkeletalMaterial& Slot : Mesh->GetMaterials())
    {
        TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
        const UMaterialInterface* Material = Slot.MaterialInterface;
        if (!Material) return Reject(TEXT("MISSING_NATIVE_MATERIAL_SLOT"));
        Row->SetStringField(TEXT("slot_name"), Slot.MaterialSlotName.ToString());
        Row->SetStringField(TEXT("imported_slot_name"), Slot.ImportedMaterialSlotName.ToString());
        Row->SetStringField(TEXT("material_path"), Material->GetPathName());
        Row->SetStringField(TEXT("material_class"), Material->GetClass()->GetName());
        Row->SetNumberField(TEXT("blend_mode"), static_cast<int32>(Material->GetBlendMode()));
        Row->SetBoolField(TEXT("is_two_sided"), Material->IsTwoSided());
        FLinearColor Color(0,0,0,0); float Roughness = 0, Metallic = 0;
        const bool HasColor = Material->GetVectorParameterValue(FHashedMaterialParameterInfo(FName(TEXT("UccBaseColorLinear"))), Color);
        const bool HasRoughness = Material->GetScalarParameterValue(FHashedMaterialParameterInfo(FName(TEXT("UccRoughness"))), Roughness);
        const bool HasMetallic = Material->GetScalarParameterValue(FHashedMaterialParameterInfo(FName(TEXT("UccMetallic"))), Metallic);
        if (!FMath::IsFinite(Color.R) || !FMath::IsFinite(Color.G) || !FMath::IsFinite(Color.B)
            || !FMath::IsFinite(Color.A) || !FMath::IsFinite(Roughness) || !FMath::IsFinite(Metallic))
            return Reject(TEXT("NONFINITE_NATIVE_MATERIAL"));
        Row->SetBoolField(TEXT("base_color_linear_present"), HasColor);
        Row->SetBoolField(TEXT("roughness_present"), HasRoughness);
        Row->SetBoolField(TEXT("metallic_present"), HasMetallic);
        TArray<TSharedPtr<FJsonValue>> RGBA;
        for (float Value : {Color.R, Color.G, Color.B, Color.A}) RGBA.Add(MakeShared<FJsonValueNumber>(Value));
        Row->SetArrayField(TEXT("base_color_linear_rgba"), RGBA);
        Row->SetNumberField(TEXT("roughness"), Roughness);
        Row->SetNumberField(TEXT("metallic"), Metallic);
        MaterialRows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Readback->SetArrayField(TEXT("materials"), MaterialRows);
    const auto Bound = Mesh->GetBounds(); const auto ImportedBound = Mesh->GetImportedBounds();
    if (Bound.Origin.ContainsNaN() || Bound.BoxExtent.ContainsNaN() || ImportedBound.Origin.ContainsNaN()
        || ImportedBound.BoxExtent.ContainsNaN() || Mesh->GetPositiveBoundsExtension().ContainsNaN()
        || Mesh->GetNegativeBoundsExtension().ContainsNaN() || !FMath::IsFinite(Bound.SphereRadius)
        || !FMath::IsFinite(ImportedBound.SphereRadius)) return Reject(TEXT("NONFINITE_NATIVE_BOUNDS"));
    TSharedRef<FJsonObject> Bounds = MakeShared<FJsonObject>();
    auto VectorArray = [](const FVector& V) { TArray<TSharedPtr<FJsonValue>> A;
        A.Add(MakeShared<FJsonValueNumber>(V.X)); A.Add(MakeShared<FJsonValueNumber>(V.Y));
        A.Add(MakeShared<FJsonValueNumber>(V.Z)); return A; };
    Bounds->SetArrayField(TEXT("origin_cm"), VectorArray(Bound.Origin));
    Bounds->SetArrayField(TEXT("box_extent_cm"), VectorArray(Bound.BoxExtent));
    Bounds->SetNumberField(TEXT("sphere_radius_cm"), Bound.SphereRadius);
    Bounds->SetArrayField(TEXT("imported_origin_cm"), VectorArray(ImportedBound.Origin));
    Bounds->SetArrayField(TEXT("imported_box_extent_cm"), VectorArray(ImportedBound.BoxExtent));
    Bounds->SetNumberField(TEXT("imported_sphere_radius_cm"), ImportedBound.SphereRadius);
    Bounds->SetBoolField(TEXT("nanite_enabled"), Mesh->IsNaniteEnabled());
    Bounds->SetBoolField(TEXT("nanite_settings_enabled"), Mesh->GetNaniteSettings().bEnabled);
    Bounds->SetBoolField(TEXT("nanite_valid_data"), Render->HasValidNaniteData());
    Bounds->SetArrayField(TEXT("positive_extension_cm"), VectorArray(Mesh->GetPositiveBoundsExtension()));
    Bounds->SetArrayField(TEXT("negative_extension_cm"), VectorArray(Mesh->GetNegativeBoundsExtension()));
    Readback->SetObjectField(TEXT("bounds"), Bounds);
    Root->SetObjectField(TEXT("readback"), Readback);
    Root->SetStringField(TEXT("status"), TEXT("CAPTURED_UNVERIFIED"));
    Root->SetStringField(TEXT("reason"), TEXT("HOST_SOURCE_PARITY_REQUIRED"));
    Root->SetBoolField(TEXT("native_data_observed"), true);
    return Finish(Root);
}
