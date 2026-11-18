#include "UccNativeAnimation.h"
#include "UccRegisteredPreviewActor.h"

#include "Animation/AnimSequence.h"
#include "AssetCompilingManager.h"
#include "Components/DirectionalLightComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/DirectionalLight.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "HAL/FileManager.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "UObject/SavePackage.h"
#include "Windows/WindowsHWrapper.h"

THIRD_PARTY_INCLUDES_START
#include <bcrypt.h>
THIRD_PARTY_INCLUDES_END

namespace UccNativeAnimation
{
    namespace
    {
        constexpr int32 MaxPacketBytes = 32 * 1024 * 1024;

        bool AddLight(UWorld& World, const FRotator& Rotation, float Intensity)
        {
            auto* Light = World.SpawnActor<ADirectionalLight>(FVector::ZeroVector, Rotation);
            if (!Light)
                return false;
            auto* Component = Light->GetComponent();
            Component->SetMobility(EComponentMobility::Movable);
            Component->SetIntensity(Intensity);
            return true;
        }
    }

    bool PreviewPacketSha(TConstArrayView<uint8> Packet, FString& Digest)
    {
        if (Packet.IsEmpty() || Packet.Num() > MaxPacketBytes)
            return false;
        uint8 Hash[32];
        if (BCryptHash(BCRYPT_SHA256_ALG_HANDLE, nullptr, 0, const_cast<uint8*>(Packet.GetData()),
            uint32(Packet.Num()), Hash, sizeof(Hash)) < 0)
            return false;
        Digest = BytesToHex(Hash, sizeof(Hash)).ToLower();
        return true;
    }

    bool StagePreview(const FInputs& Inputs, const FString& PacketPath, const FString& Output)
    {
        const FString Target = FPackageName::LongPackageNameToFilename(PreviewScene,
            FPackageName::GetMapPackageExtension());
        if (FPaths::IsRelative(PacketPath) || IFileManager::Get().FileExists(*Target))
            return false;

        TUniquePtr<FArchive> File(IFileManager::Get().CreateFileReader(*PacketPath));
        if (!File || File->TotalSize() <= 0 || File->TotalSize() > MaxPacketBytes)
            return false;
        TArray<uint8> Packet;
        Packet.SetNumUninitialized(int32(File->TotalSize()));
        File->Serialize(Packet.GetData(), Packet.Num());
        if (!File->Close() || File->IsError())
            return false;
        FString Digest;
        if (!PreviewPacketSha(Packet, Digest))
            return false;

        FAssetCompilingManager::Get().FinishAllCompilation();
        if (!UsesExactCompression(*Inputs.Clip))
            return false;

        auto* Package = CreatePackage(PreviewScene);
        const auto Values = FWorldInitializationValues().AllowAudioPlayback(false).RequiresHitProxies(false)
            .CreatePhysicsScene(false).CreateNavigation(false).CreateAISystem(false).CreateFXSystem(false);
        UWorld* World = UWorld::CreateWorld(EWorldType::Editor, false, FName(TEXT("CharacterScene")), Package, true,
            ERHIFeatureLevel::Num, &Values);
        if (!World)
            return false;
        World->SetFlags(RF_Public | RF_Standalone);

        int32 NativeVertices = 0;
        auto* Actor = World->SpawnActor<AUccRegisteredPreviewActor>();
        if (!Actor || !Actor->Configure(*Inputs.Mesh, *Inputs.Clip, MoveTemp(Packet), NativeVertices)
            || !AddLight(*World, FRotator(-36.0, 150.0, 0.0), 3.0f)
            || !AddLight(*World, FRotator(-17.0, -156.0, 0.0), 1.1f))
        {
            World->DestroyWorld(false);
            return false;
        }
        FSavePackageArgs Save;
        Save.TopLevelFlags = RF_Public | RF_Standalone;
        const bool Saved = UPackage::SavePackage(Package, World, *Target, Save);
        World->DestroyWorld(false);
        if (!Saved)
            return false;

        auto Record = MakeShared<FJsonObject>();
        Record->SetNumberField(TEXT("schema_version"), 1);
        Record->SetStringField(TEXT("policy"), TEXT("UCC_UNREAL_REGISTERED_PREVIEW_STAGE_V1"));
        Record->SetStringField(TEXT("scene"), PreviewScene);
        Record->SetStringField(TEXT("packet_sha256"), Digest);
        Record->SetNumberField(TEXT("native_vertices"), NativeVertices);
        return WriteJson(Output / TEXT("preview-stage.json"), Record);
    }
}
