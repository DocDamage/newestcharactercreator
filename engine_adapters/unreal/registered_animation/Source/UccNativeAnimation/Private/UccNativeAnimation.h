#pragma once

#include "CoreMinimal.h"

class UAnimSequence;
class USkeletalMesh;
class USkeleton;
class FJsonObject;

namespace UccNativeAnimation
{
    struct FInputs
    {
        USkeletalMesh* Mesh = nullptr;
        USkeleton* Skeleton = nullptr;
        UAnimSequence* Clip = nullptr;
    };

    constexpr TCHAR PreviewScene[] = TEXT("/Game/UccAnimation/CharacterScene");

    bool StagePreview(const FInputs& Inputs, const FString& PacketPath, const FString& Output);
    bool PreviewPacketSha(TConstArrayView<uint8> Packet, FString& Digest);
    void StartPreviewVerifier();

    constexpr int32 Frames = 300;
    constexpr int32 Fps = 30;
    constexpr float Duration = float(Frames) / Fps;

    bool WriteJson(const FString& Path, const TSharedRef<FJsonObject>& Value);
    bool UsesExactCompression(const UAnimSequence& Clip);
    bool CollectSavedInputs(FInputs& Inputs);
    bool ImportFbx(const FString& FbxPath, const FString& Output);
    bool Observe(const FInputs& Inputs, const FString& Output);
}
