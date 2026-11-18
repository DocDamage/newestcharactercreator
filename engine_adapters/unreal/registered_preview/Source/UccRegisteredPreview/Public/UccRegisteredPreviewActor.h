#pragma once

#include "GameFramework/Actor.h"
#include "UccRegisteredPreviewActor.generated.h"

class UAnimSequence;
class UCameraComponent;
class UProceduralMeshComponent;
class USkeletalMesh;
class USkeletalMeshComponent;
class USceneComponent;

UCLASS(NotBlueprintable)
class UCCREGISTEREDPREVIEW_API AUccRegisteredPreviewActor final : public AActor
{
    GENERATED_BODY()

public:
    AUccRegisteredPreviewActor();
    virtual ~AUccRegisteredPreviewActor() override;

    bool Configure(USkeletalMesh& Mesh, UAnimSequence& Clip, TArray<uint8>&& Packet, int32& NativeVertices);
    TConstArrayView<uint8> GetEmbeddedPacket() const { return Operands; }
    const UCameraComponent* GetPreviewCamera() const { return Camera; }
    bool ReadSubmitted(TArray<float>& Vertices, float& Time, uint64& Serial) const;
    UProceduralMeshComponent* GetCorrectedComponent() const { return Draw; }

protected:
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;

private:
    struct FState;
    struct FStateDeleter { void operator()(FState* Value) const; };
    TUniquePtr<FState, FStateDeleter> State;

    UPROPERTY(VisibleAnywhere, Category="UCC Preview")
    TObjectPtr<USceneComponent> PreviewRoot;
    UPROPERTY(VisibleAnywhere, Category="UCC Preview")
    TObjectPtr<USkeletalMeshComponent> Source;
    UPROPERTY(VisibleAnywhere, Category="UCC Preview")
    TObjectPtr<UProceduralMeshComponent> Draw;
    UPROPERTY(VisibleAnywhere, Category="UCC Preview")
    TObjectPtr<UCameraComponent> Camera;
    UPROPERTY()
    TObjectPtr<USkeletalMesh> SavedMesh;
    UPROPERTY()
    TObjectPtr<UAnimSequence> SavedClip;
    UPROPERTY()
    TArray<uint8> Operands;

    bool InitializeLiveMesh();
    bool SubmitCurrent();
    void StopPreview();
};
