#include "UccNativeAnimation.h"

#include "Animation/AnimData/IAnimationDataModel.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimSingleNodeInstance.h"
#include "Animation/MorphTarget.h"
#include "Animation/SkeletalMeshActor.h"
#include "Animation/Skeleton.h"
#include "AssetCompilingManager.h"
#include "Components/SkeletalMeshComponent.h"
#include "CoreGlobals.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/Engine.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/EngineBaseTypes.h"
#include "Engine/World.h"
#include "GameFramework/WorldSettings.h"
#include "HAL/FileManager.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "Rendering/SkeletalMeshRenderData.h"

namespace UccNativeAnimation
{
    namespace
    {
        constexpr float Step = 1.0f / Fps;

        struct FPreviewWorld
        {
            FPreviewWorld()
            {
                auto Values = FWorldInitializationValues().AllowAudioPlayback(false).RequiresHitProxies(false)
                    .CreatePhysicsScene(false).CreateNavigation(false).CreateAISystem(false)
                    .ShouldSimulatePhysics(false).SetTransactional(false).CreateFXSystem(false);
                World = UWorld::CreateWorld(EWorldType::GamePreview, false, NAME_None, nullptr, true,
                    ERHIFeatureLevel::Num, &Values);
                if (World)
                    GEngine->CreateNewWorldContext(EWorldType::GamePreview).SetCurrentWorld(World);
            }

            ~FPreviewWorld()
            {
                if (World)
                {
                    GEngine->DestroyWorldContext(World);
                    World->DestroyWorld(false);
                }
            }

            UWorld* World = nullptr;
        };

        bool CheckClip(const UAnimSequence& Clip)
        {
            const IAnimationDataModel* Model = Clip.GetDataModel();
            if (!Model || Model->GetFrameRate() != FFrameRate(Fps, 1)
                || Model->GetNumberOfFrames() != Frames || Model->GetNumberOfKeys() != Frames+1
                || !FMath::IsNearlyEqual(Clip.GetPlayLength(), Duration, 1.e-4f))
            {
                UE_LOG(LogTemp, Error, TEXT("Native animation does not retain 301 keys over ten seconds at 30 Hz"));
                return false;
            }
            TArray<FName> Tracks;
            Model->GetBoneTrackNames(Tracks);
            if (Tracks.IsEmpty())
                return false;
            for (FName Name : Tracks)
            {
                const FTransform First = Model->GetBoneTrackTransform(Name, FFrameNumber(0));
                const FTransform Endpoint = Model->GetBoneTrackTransform(Name, FFrameNumber(Frames));
                if (First.ContainsNaN() || Endpoint.ContainsNaN() || !First.Equals(Endpoint, 1.e-4))
                {
                    UE_LOG(LogTemp, Error, TEXT("Native animation endpoint differs from its first pose"));
                    return false;
                }
            }
            return true;
        }

        bool MatrixValues(const FTransform& Transform, TArray<float>& Out)
        {
            // Unreal uses row-vector matrices. Emit column-vector matrices in row-major order.
            const FMatrix Matrix = Transform.ToMatrixWithScale();
            for (int Row = 0; Row < 4; ++Row)
                for (int Column = 0; Column < 4; ++Column)
                {
                    const float Value = float(Matrix.M[Column][Row]);
                    if (!FMath::IsFinite(Value))
                        return false;
                    Out.Add(Value);
                }
            return true;
        }

        TArray<TSharedPtr<FJsonValue>> JsonValues(const TArray<float>& Input)
        {
            TArray<TSharedPtr<FJsonValue>> Values;
            for (float Value : Input)
                Values.Add(MakeShared<FJsonValueNumber>(Value));
            return Values;
        }

        bool Bind(const USkeletalMesh& Mesh, const FSkeletalMeshLODRenderData& Lod,
                  const FSkinWeightVertexBuffer& Weights, const FString& Output)
        {
            const auto& Reference = Mesh.GetRefSkeleton();
            auto Document = MakeShared<FJsonObject>();
            Document->SetNumberField(TEXT("schema_version"), 1);
            Document->SetStringField(TEXT("units"), TEXT("unreal_world_centimeters"));
            const auto& Local = Reference.GetRefBonePose();
            TArray<FTransform> World;
            TArray<TSharedPtr<FJsonValue>> Bones, Positions;
            for (int32 Index = 0; Index < Local.Num(); ++Index)
            {
                const int32 Parent = Reference.GetParentIndex(Index);
                if (Parent >= Index || Parent < INDEX_NONE)
                    return false;
                World.Add(Parent == INDEX_NONE ? Local[Index] : Local[Index] * World[Parent]);
                TArray<float> Matrix;
                if (!MatrixValues(World.Last(), Matrix))
                    return false;
                auto Bone = MakeShared<FJsonObject>();
                Bone->SetStringField(TEXT("name"), Reference.GetBoneName(Index).ToString());
                Bone->SetNumberField(TEXT("parent"), Parent);
                Bone->SetArrayField(TEXT("rest_world"), JsonValues(Matrix));
                Bones.Add(MakeShared<FJsonValueObject>(Bone));
            }
            for (uint32 Index = 0; Index < Lod.GetNumVertices(); ++Index)
            {
                const FVector3f Position = Lod.StaticVertexBuffers.PositionVertexBuffer.VertexPosition(Index);
                if (Position.ContainsNaN())
                    return false;
                Positions.Add(MakeShared<FJsonValueArray>(JsonValues({Position.X, Position.Y, Position.Z})));
            }
            TSet<int32> UsedBones;
            for (const FSkelMeshRenderSection& Section : Lod.RenderSections)
            {
                for (uint32 Index = Section.BaseVertexIndex; Index < Section.BaseVertexIndex + Section.NumVertices; ++Index)
                {
                    if (Index >= Lod.GetNumVertices())
                        return false;
                    uint32 Offset, Count;
                    Weights.GetVertexInfluenceOffsetCount(Index, Offset, Count);
                    for (uint32 Influence = 0; Influence < Count; ++Influence)
                    {
                        if (!Weights.GetBoneWeight(Index, Influence))
                            continue;
                        const uint32 LocalBone = Weights.GetBoneIndex(Index, Influence);
                        if (!Section.BoneMap.IsValidIndex(int32(LocalBone)) || Section.BoneMap[LocalBone] >= Local.Num())
                            return false;
                        UsedBones.Add(Section.BoneMap[LocalBone]);
                    }
                }
            }
            TArray<TSharedPtr<FJsonValue>> Influences;
            for (int32 Index = 0; Index < Local.Num(); ++Index)
                if (UsedBones.Contains(Index))
                    Influences.Add(MakeShared<FJsonValueNumber>(Index));
            TArray<TSharedPtr<FJsonValue>> MorphNames;
            TSet<FName> UsedMorphNames;
            for (const UMorphTarget* Morph : Mesh.GetMorphTargets())
            {
                if (!Morph || Morph->GetFName().IsNone() || UsedMorphNames.Contains(Morph->GetFName()))
                    return false;
                UsedMorphNames.Add(Morph->GetFName());
                MorphNames.Add(MakeShared<FJsonValueString>(Morph->GetName()));
            }
            Document->SetArrayField(TEXT("morph_names"), MorphNames);
            Document->SetArrayField(TEXT("bones"), Bones);
            Document->SetArrayField(TEXT("positions_cm"), Positions);
            Document->SetArrayField(TEXT("used_skin_bones"), Influences);
            return WriteJson(Output / TEXT("bind.json"), Document);
        }

        bool Capture(USkeletalMeshComponent& Component, const FSkeletalMeshLODRenderData& Lod,
                     const FSkinWeightVertexBuffer& Weights, int32 Bones, TArray<float>& Pose, TArray<float>& Skin)
        {
            const TArray<FTransform>& ComponentPose = Component.GetComponentSpaceTransforms();
            if (ComponentPose.Num() != Bones)
                return false;
            const FTransform& ToWorld = Component.GetComponentTransform();
            Pose.Reset(Bones*16);
            for (const FTransform& Bone : ComponentPose)
                if (!MatrixValues(Bone * ToWorld, Pose))
                    return false;

            TArray<FMatrix44f> RefToLocal;
            Component.GetCurrentRefToLocalMatrices(RefToLocal, 0);
            if (RefToLocal.Num() != Bones)
                return false;
            TArray<FVector3f> Positions;
            USkeletalMeshComponent::ComputeSkinnedPositions(&Component, Positions, RefToLocal, Lod, Weights);
            if (Positions.Num() != int32(Lod.GetNumVertices()))
                return false;
            Skin.Reset(Positions.Num()*3);
            for (const FVector3f& Position : Positions)
            {
                const FVector3f World(ToWorld.TransformPosition(FVector(Position)));
                if (World.ContainsNaN())
                    return false;
                Skin.Append({World.X, World.Y, World.Z});
            }
            return true;
        }
    }

    bool Observe(const FInputs& Inputs, const FString& Output)
    {
        if (!CheckClip(*Inputs.Clip))
            return false;
        FAssetCompilingManager::Get().FinishAllCompilation();
        if (!UsesExactCompression(*Inputs.Clip))
        {
            UE_LOG(LogTemp, Error, TEXT("Saved animation frame-preserving compression is unavailable or changed"));
            return false;
        }
        const auto& Reference = Inputs.Mesh->GetRefSkeleton();
        const int32 Bones = Reference.GetNum();
        const FSkeletalMeshRenderData* Rendering = Inputs.Mesh->GetResourceForRendering();
        if (Bones <= 0 || Bones > 512 || !Rendering || !Rendering->LODRenderData.IsValidIndex(0))
            return false;
        const auto& Lod = Rendering->LODRenderData[0];
        if (Lod.GetNumVertices() == 0 || Lod.GetNumVertices() > 100000)
            return false;

        FPreviewWorld Preview;
        if (!Preview.World)
            return false;
        ASkeletalMeshActor* Actor = Preview.World->SpawnActor<ASkeletalMeshActor>();
        if (!Actor)
            return false;
        auto& Component = *Actor->GetSkeletalMeshComponent();
        Component.SetSkeletalMeshAsset(Inputs.Mesh);
        Component.VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
        Component.bEnableUpdateRateOptimizations = false;
        Preview.World->InitializeActorsForPlay(FURL());
        Preview.World->BeginPlay();
        if (!Preview.World->HasBegunPlay())
            Preview.World->GetWorldSettings()->NotifyBeginPlay();
        Component.PlayAnimation(Inputs.Clip, true);
        UAnimSingleNodeInstance* Single = Component.GetSingleNodeInstance();
        const FSkinWeightVertexBuffer* Weights = Component.GetSkinWeightBuffer(0);
        if (!Single || Single->GetCurrentAsset() != Inputs.Clip || !Single->IsLooping()
            || !Weights || !Weights->Use16BitBoneWeight()
            || !Lod.StaticVertexBuffers.StaticMeshVertexBuffer.GetUseFullPrecisionUVs())
        {
            UE_LOG(LogTemp, Error, TEXT("Reopened skeletal LOD0 lacks the verified animation or full-precision streams"));
            return false;
        }
        if (!Bind(*Inputs.Mesh, Lod, *Weights, Output))
            return false;

        TUniquePtr<FArchive> PoseFile(IFileManager::Get().CreateFileWriter(*(Output / TEXT("pose_world.f32")), FILEWRITE_NoReplaceExisting));
        TUniquePtr<FArchive> SkinFile(IFileManager::Get().CreateFileWriter(*(Output / TEXT("raw_skin_world.f32")), FILEWRITE_NoReplaceExisting));
        if (!PoseFile || !SkinFile)
            return false;
        TArray<float> Pose, Skin;
        for (int32 Frame = 0; Frame < Frames; ++Frame)
        {
            const float Position = float(Frame)/Fps;
            Component.SetPosition(Position, false);
            Component.TickAnimation(0.0f, false);
            Component.RefreshBoneTransforms();
            if (!FMath::IsNearlyEqual(Single->GetCurrentTime(), Position, 1.e-4f)
                || !Capture(Component, Lod, *Weights, Bones, Pose, Skin))
            {
                UE_LOG(LogTemp, Error, TEXT("Native skeletal evaluation failed at sample %d"), Frame);
                return false;
            }
            PoseFile->Serialize(Pose.GetData(), Pose.Num()*sizeof(float));
            SkinFile->Serialize(Skin.GetData(), Skin.Num()*sizeof(float));
        }
        if (!PoseFile->Close() || !SkinFile->Close() || PoseFile->IsError() || SkinFile->IsError())
            return false;

        const float Start = float(Frames-3)/Fps;
        Component.SetPosition(Start, false);
        TArray<TSharedPtr<FJsonValue>> Playback;
        for (int32 Tick = 1; Tick <= 7; ++Tick)
        {
            // A commandlet has no outer engine frame loop to advance this counter.
            // Skeletal components use it to avoid updating twice in the same frame.
            ++GFrameCounter;
            Preview.World->Tick(LEVELTICK_All, Step);
            const float Clock = Single->GetCurrentTime();
            // A clock sitting exactly at the terminal key may wrap on the next tick.
            const float Expected = float(Frames-3+Tick)/Fps;
            const float Error = FMath::Abs(Clock - Expected);
            if (!Single->IsPlaying() || !Single->IsLooping()
                || !(Error < 1.e-3f || FMath::Abs(Error-Duration) < 1.e-3f)
                || !Capture(Component, Lod, *Weights, Bones, Pose, Skin))
            {
                UE_LOG(LogTemp, Error, TEXT("World tick %d left position %.8f (begun=%d, initialized=%d, registered=%d, tick=%d, playing=%d)"),
                    Tick, Clock, Preview.World->HasBegunPlay(), Preview.World->AreActorsInitialized(),
                    Component.IsRegistered(), Component.IsComponentTickEnabled(), Single->IsPlaying());
                return false;
            }
            auto Row = MakeShared<FJsonObject>();
            Row->SetNumberField(TEXT("time_seconds"), Clock);
            Row->SetArrayField(TEXT("pose_world"), JsonValues(Pose));
            // Capture one pose per tick; the fixed-clock stream contains full skin readback.
            Playback.Add(MakeShared<FJsonValueObject>(Row));
        }
        auto Report = MakeShared<FJsonObject>();
        Report->SetNumberField(TEXT("schema_version"), 1);
        Report->SetStringField(TEXT("policy"), TEXT("UCC_UNREAL_NATIVE_ANIMATION_OBSERVATION_V1"));
        Report->SetStringField(TEXT("mesh"), Inputs.Mesh->GetPathName());
        Report->SetStringField(TEXT("skeleton"), Inputs.Clip->GetSkeleton()->GetPathName());
        Report->SetStringField(TEXT("clip"), Inputs.Clip->GetPathName());
        Report->SetNumberField(TEXT("frames"), Frames);
        Report->SetNumberField(TEXT("fps"), Fps);
        Report->SetNumberField(TEXT("native_keys"), Frames+1);
        Report->SetNumberField(TEXT("bones"), Bones);
        Report->SetNumberField(TEXT("native_vertices"), Lod.GetNumVertices());
        Report->SetBoolField(TEXT("endpoint_matches"), true);
        Report->SetStringField(TEXT("bone_compression"), TEXT("AnimCompress_LeastDestructive"));
        Report->SetArrayField(TEXT("preview_world_ticks"), Playback);
        return WriteJson(Output / TEXT("observation.json"), Report);
    }
}
