#include "UccRegisteredPreviewActor.h"
#include "UccRegisteredCorrection.h"

#include "Animation/AnimSequence.h"
#include "Animation/AnimSingleNodeInstance.h"
#include "Camera/CameraComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Materials/Material.h"
#include "ProceduralMeshComponent.h"
#include "Rendering/SkeletalMeshRenderData.h"

namespace
{
    namespace Correction = UccRegisteredCorrection;

    const FSkeletalMeshLODRenderData* Lod0(USkeletalMesh& Mesh)
    {
        const auto* RenderData = Mesh.GetResourceForRendering();
        return RenderData && RenderData->LODRenderData.IsValidIndex(0) ? &RenderData->LODRenderData[0] : nullptr;
    }

    std::span<const std::uint8_t> Bytes(TConstArrayView<uint8> Input)
    {
        return {Input.GetData(), size_t(Input.Num())};
    }
}

struct AUccRegisteredPreviewActor::FState
{
    Correction::FKernel Kernel;
    const FSkeletalMeshLODRenderData* Lod = nullptr;
    TArray<FMatrix44f> RefToLocal;
    TArray<FVector3f> Native;
    TArray<Correction::FVector> Raw, Corrected, Normals;
    TArray<FVector> DrawPositions, DrawNormals;
    TArray<int32> Indices;
    TArray<FVector2D> UV;
    float Time = 0;
    uint64 Serial = 0;
    bool ViewSet = false;
};

void AUccRegisteredPreviewActor::FStateDeleter::operator()(FState* Value) const
{
    delete Value;
}

AUccRegisteredPreviewActor::AUccRegisteredPreviewActor()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickGroup = TG_PostUpdateWork;
    PreviewRoot = CreateDefaultSubobject<USceneComponent>(TEXT("PreviewRoot"));
    SetRootComponent(PreviewRoot);

    Source = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("NativeAnimation"));
    Source->SetupAttachment(PreviewRoot);
    Source->SetHiddenInGame(true);
    Source->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Source->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    Source->bEnableUpdateRateOptimizations = false;
    Source->SetForcedLOD(1);

    Draw = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("CorrectedSurface"));
    Draw->SetupAttachment(PreviewRoot);
    Draw->SetCollisionEnabled(ECollisionEnabled::NoCollision);

    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("PreviewCamera"));
    Camera->SetupAttachment(PreviewRoot);
    Camera->FieldOfView = 35.0f;
    Camera->bConstrainAspectRatio = false;
    Camera->bUsePawnControlRotation = false;
}

AUccRegisteredPreviewActor::~AUccRegisteredPreviewActor() = default;

bool AUccRegisteredPreviewActor::Configure(USkeletalMesh& Mesh, UAnimSequence& Clip,
                                            TArray<uint8>&& Packet, int32& NativeVertices)
{
    const auto* Lod = Lod0(Mesh);
    Correction::FKernel Check;
    if (!Lod || !Mesh.GetSkeleton() || Clip.GetSkeleton() != Mesh.GetSkeleton() || !Check.LoadPacket(Bytes(Packet))
        || Check.GetNativeVertexCount() != Lod->GetNumVertices())
        return false;

    auto* Material = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial"));
    if (!Material)
        return false;
    Draw->SetMaterial(0, Material);

    SavedMesh = &Mesh;
    SavedClip = &Clip;
    Operands = MoveTemp(Packet);
    NativeVertices = int32(Lod->GetNumVertices());
    Source->SetSkeletalMeshAsset(SavedMesh);

    const FBoxSphereBounds Bounds = Mesh.GetBounds();
    const double R = FMath::Max(1.0, double(Bounds.SphereRadius));
    const FVector Eye = FVector(2.9, .70, .95) * R;
    Camera->SetRelativeLocation(Bounds.Origin + Eye);
    Camera->SetRelativeRotation((-Eye).Rotation());
    return true;
}

void AUccRegisteredPreviewActor::BeginPlay()
{
    Super::BeginPlay();
    AddTickPrerequisiteComponent(Source);
    if (!InitializeLiveMesh())
        StopPreview();
}

bool AUccRegisteredPreviewActor::InitializeLiveMesh()
{
    if (!SavedMesh || !SavedClip || !GetActorTransform().Equals(FTransform::Identity))
        return false;
    State.Reset(new FState());
    State->Lod = Lod0(*SavedMesh);
    if (!State->Lod || !State->Kernel.LoadPacket(Bytes(Operands))
        || State->Kernel.GetNativeVertexCount() != State->Lod->GetNumVertices())
        return false;
    const int32 Count = int32(State->Lod->GetNumVertices());
    TArray<uint32> NativeIndices;
    State->Lod->MultiSizeIndexContainer.GetIndexBuffer(NativeIndices);
    if (NativeIndices.IsEmpty() || NativeIndices.Num()%3 != 0)
        return false;
    State->Indices.Reserve(NativeIndices.Num());
    for (const uint32 Index : NativeIndices)
    {
        if (Index >= uint32(Count))
            return false;
        State->Indices.Add(int32(Index));
    }
    State->UV.Reserve(Count);
    const auto& Buffer = State->Lod->StaticVertexBuffers.StaticMeshVertexBuffer;
    for (int32 Vertex = 0; Vertex < Count; ++Vertex)
        State->UV.Add(FVector2D(Buffer.GetVertexUV(Vertex, 0)));

    State->Raw.SetNumUninitialized(Count);
    State->Corrected.SetNumUninitialized(Count);
    State->Normals.SetNumUninitialized(Count);
    State->DrawPositions.SetNumUninitialized(Count);
    State->DrawNormals.SetNumUninitialized(Count);
    Source->SetSkeletalMeshAsset(SavedMesh);
    Source->PlayAnimation(SavedClip, true);
    return true;
}

void AUccRegisteredPreviewActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!State)
        return;
    if (!State->ViewSet)
        if (APlayerController* Player = GetWorld()->GetFirstPlayerController())
        {
            Player->SetViewTarget(this);
            State->ViewSet = true;
        }
    if (!SubmitCurrent())
        StopPreview();
}

bool AUccRegisteredPreviewActor::SubmitCurrent()
{
    const UAnimSingleNodeInstance* Player = Source->GetSingleNodeInstance();
    const FSkinWeightVertexBuffer* Weights = Source->GetSkinWeightBuffer(0);
    if (!Player || !Player->IsPlaying() || !Player->IsLooping() || !Weights
        || !Source->GetComponentTransform().Equals(FTransform::Identity))
        return false;

    Source->GetCurrentRefToLocalMatrices(State->RefToLocal, 0);
    if (State->RefToLocal.Num() != SavedMesh->GetRefSkeleton().GetNum())
        return false;
    USkeletalMeshComponent::ComputeSkinnedPositions(Source, State->Native, State->RefToLocal, *State->Lod, *Weights);
    const int32 Count = State->Raw.Num();
    if (State->Native.Num() != Count)
        return false;
    for (int32 Index = 0; Index < Count; ++Index)
    {
        const auto& P = State->Native[Index];
        State->Raw[Index] = {P.X, P.Y, P.Z};
    }
    if (!State->Kernel.Evaluate({State->Raw.GetData(), size_t(Count)},
        {State->Corrected.GetData(), size_t(Count)}, {State->Normals.GetData(), size_t(Count)}))
        return false;
    for (int32 Index = 0; Index < Count; ++Index)
    {
        const auto& P = State->Corrected[Index];
        const auto& N = State->Normals[Index];
        State->DrawPositions[Index] = FVector(P.X, P.Y, P.Z);
        State->DrawNormals[Index] = FVector(N.X, N.Y, N.Z);
    }
    if (!State->Serial)
        Draw->CreateMeshSection_LinearColor(0, State->DrawPositions, State->Indices, State->DrawNormals,
            State->UV, {}, {}, false);
    else
        Draw->UpdateMeshSection_LinearColor(0, State->DrawPositions, State->DrawNormals, State->UV, {}, {});
    State->Time = Player->GetCurrentTime();
    ++State->Serial;
    return true;
}

bool AUccRegisteredPreviewActor::ReadSubmitted(TArray<float>& Vertices, float& Time, uint64& Serial) const
{
    if (!State || !State->Serial || !Draw->IsRegistered() || !Draw->IsVisible() || !Draw->IsMeshSectionVisible(0))
        return false;
    const auto* Section = Draw->GetProcMeshSection(0);
    if (!Section || Section->ProcVertexBuffer.Num() != State->Raw.Num())
        return false;
    Vertices.Reset(State->Raw.Num()*6);
    for (const auto& Vertex : Section->ProcVertexBuffer)
    {
        const auto& P = Vertex.Position;
        const auto& N = Vertex.Normal;
        Vertices.Append({float(P.X), float(P.Y), float(P.Z), float(N.X), float(N.Y), float(N.Z)});
    }
    Time = State->Time;
    Serial = State->Serial;
    return true;
}

void AUccRegisteredPreviewActor::StopPreview()
{
    Draw->ClearAllMeshSections();
    State.Reset();
    SetActorTickEnabled(false);
    UE_LOG(LogTemp, Error, TEXT("UCC corrected character playback stopped because its saved source or runtime operands failed verification"));
}
