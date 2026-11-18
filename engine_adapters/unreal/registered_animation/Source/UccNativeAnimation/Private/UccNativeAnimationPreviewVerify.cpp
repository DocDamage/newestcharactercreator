#include "UccNativeAnimation.h"
#include "UccRegisteredPreviewActor.h"

#include "Camera/CameraComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Containers/Ticker.h"
#include "Dom/JsonObject.h"
#include "DynamicRHI.h"
#include "Editor.h"
#include "Editor/EditorEngine.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "PlayInEditorDataTypes.h"
#include "ProceduralMeshComponent.h"
#include "RenderingThread.h"
#include "TextureResource.h"

namespace UccNativeAnimation
{
    namespace
    {
        constexpr int32 RasterExtent = 256;

        bool Capture(AUccRegisteredPreviewActor& Actor, TArray<FColor>& Pixels)
        {
            const auto* Camera = Actor.GetPreviewCamera();
            auto* Surface = Actor.GetCorrectedComponent();
            if (!Camera || !Surface || !GDynamicRHI || GDynamicRHI->GetInterfaceType() == ERHIInterfaceType::Null)
                return false;
            auto* Target = NewObject<UTextureRenderTarget2D>(&Actor);
            Target->RenderTargetFormat = RTF_RGBA8;
            Target->ClearColor = FLinearColor::Black;
            Target->InitAutoFormat(RasterExtent, RasterExtent);
            Target->UpdateResourceImmediate(true);

            auto* Capture = NewObject<USceneCaptureComponent2D>(&Actor);
            Capture->bCaptureEveryFrame = false;
            Capture->bCaptureOnMovement = false;
            Capture->CaptureSource = SCS_FinalColorLDR;
            Capture->PrimitiveRenderMode = ESceneCapturePrimitiveRenderMode::PRM_UseShowOnlyList;
            Capture->ShowOnlyComponent(Surface);
            Capture->TextureTarget = Target;
            Capture->FOVAngle = Camera->FieldOfView;
            Capture->PostProcessSettings.bOverride_AutoExposureMethod = true;
            Capture->PostProcessSettings.AutoExposureMethod = AEM_Manual;
            Capture->PostProcessSettings.bOverride_AutoExposureBias = true;
            Capture->PostProcessSettings.AutoExposureBias = 0.0f;
            Capture->RegisterComponentWithWorld(Actor.GetWorld());
            Capture->SetWorldTransform(Camera->GetComponentTransform());
            Capture->CaptureScene();
            FlushRenderingCommands();
            const bool Valid = Target->GameThread_GetRenderTargetResource()->ReadPixels(Pixels)
                && Pixels.Num() == RasterExtent*RasterExtent;
            Capture->DestroyComponent();
            return Valid;
        }

        int32 Difference(FColor A, FColor B)
        {
            return FMath::Max3(FMath::Abs(int32(A.R)-B.R), FMath::Abs(int32(A.G)-B.G), FMath::Abs(int32(A.B)-B.B));
        }

        bool RasterCounts(const TArray<FColor>& A, const TArray<FColor>& B, int32& Foreground, int32& Motion)
        {
            if (A.Num() != RasterExtent*RasterExtent || B.Num() != A.Num())
                return false;
            int32 FrontA = 0, FrontB = 0;
            Motion = 0;
            for (int32 Index = 0; Index < A.Num(); ++Index)
            {
                const bool IsA = Difference(A[Index], A[0]) >= 8;
                const bool IsB = Difference(B[Index], B[0]) >= 8;
                FrontA += IsA;
                FrontB += IsB;
                Motion += (IsA || IsB) && Difference(A[Index], B[Index]) >= 8;
            }
            Foreground = FMath::Min(FrontA, FrontB);
            return Foreground > 64 && Motion > 16;
        }

        struct FPieVerifier
        {
            explicit FPieVerifier(FString InOutput)
                : Output(MoveTemp(InOutput)), Deadline(FPlatformTime::Seconds()+210.0)
            {
                Seen.Init(false, Frames);
            }

            bool Tick()
            {
                if (Finishing)
                {
                    if (!GEditor || !GEditor->PlayWorld)
                    {
                        FPlatformMisc::RequestExitWithStatus(false, 0);
                        return false;
                    }
                    if (FPlatformTime::Seconds() >= Deadline)
                        return Fail(TEXT("PIE session did not stop"));
                    return true;
                }
                if (FPlatformTime::Seconds() >= Deadline)
                    return Fail(TEXT("timed out waiting for the owned scene and all native PIE samples"));
                if (!GEditor || !GEditor->GetEditorWorldContext().World())
                    return true;
                if (!Requested)
                {
                    auto* EditorWorld = GEditor->GetEditorWorldContext().World();
                    if (EditorWorld->GetOutermost()->GetName() != PreviewScene)
                        return true;
                    if (!GDynamicRHI || GDynamicRHI->GetInterfaceType() == ERHIInterfaceType::Null)
                        return Fail(TEXT("rendering must use a real RHI"));
                    FApp::SetFixedDeltaTime(1.0/double(Fps));
                    FApp::SetUseFixedTimeStep(true);
                    FRequestPlaySessionParams Params;
                    Params.WorldType = EPlaySessionWorldType::PlayInEditor;
                    GEditor->RequestPlaySession(Params);
                    Requested = true;
                    return true;
                }

                UWorld* World = GEditor->PlayWorld;
                if (!World)
                    return true;
                if (World->WorldType != EWorldType::PIE || !World->GetOutermost()->GetName().EndsWith(TEXT("_CharacterScene")))
                    return Fail(TEXT("native PIE opened a different scene"));
                AUccRegisteredPreviewActor* Actor = nullptr;
                for (TActorIterator<AUccRegisteredPreviewActor> It(World); It; ++It)
                {
                    if (Actor)
                        return Fail(TEXT("native PIE contains more than one corrected preview actor"));
                    Actor = *It;
                }
                if (!Actor)
                    return Fail(TEXT("native PIE did not reopen the saved corrected preview actor"));
                if (PacketSha.IsEmpty() && !PreviewPacketSha(Actor->GetEmbeddedPacket(), PacketSha))
                    return Fail(TEXT("embedded owned correction packet has no exact digest"));

                float Time;
                uint64 Serial;
                if (!Actor->ReadSubmitted(Sample, Time, Serial) || Serial == PreviousSerial)
                    return true;
                if (!FMath::IsFinite(Time) || Time < 0.0f || Time > 10.0f
                    || Sample.IsEmpty() || Sample.Num()%6 != 0 || Sample.Num()/6 > 100000
                    || Sample.ContainsByPredicate([](float Value) { return !FMath::IsFinite(Value); }))
                    return Fail(TEXT("corrected native PIE produced an invalid finite sample"));
                const int32 Frame = FMath::RoundToInt(Time*Fps);
                if (FMath::Abs(Time*Fps-Frame) > 0.02f)
                    return Fail(TEXT("ordinary native PIE clock is off the admitted 30 Hz sample lattice"));
                const int32 Index = Frame%Frames;
                if (PreviousSerial)
                {
                    if (Serial != PreviousSerial+1 || Index != (PreviousIndex+1)%Frames)
                        return Fail(TEXT("ordinary native PIE skipped or replayed an animation sample"));
                    Wrapped |= Index == 0 && PreviousIndex == Frames-1;
                }
                PreviousSerial = Serial;
                PreviousIndex = Index;

                if (!OutputFile)
                {
                    NativeVertices = Sample.Num()/6;
                    OutputFile.Reset(IFileManager::Get().CreateFileWriter(
                        *(Output / TEXT("corrected_skin_world.f32")), FILEWRITE_NoReplaceExisting));
                    if (!OutputFile)
                        return Fail(TEXT("could not create exclusive corrected native sample stream"));
                }
                if (Sample.Num() != NativeVertices*6)
                    return Fail(TEXT("corrected native topology changed inside PIE"));
                if (!Seen[Index])
                {
                    const int64 ByteCount = int64(Sample.Num())*sizeof(float);
                    OutputFile->Seek(Index*ByteCount);
                    OutputFile->Serialize(Sample.GetData(), ByteCount);
                    if (OutputFile->IsError())
                        return Fail(TEXT("failed writing corrected native sample"));
                    Seen[Index] = true;
                    ++Samples;
                }
                if ((Index == 75 && RasterA.IsEmpty() && !Capture(*Actor, RasterA))
                    || (Index == 225 && RasterB.IsEmpty() && !Capture(*Actor, RasterB)))
                    return Fail(TEXT("actual RHI could not read the lit corrected scene pixels"));
                if (Samples == Frames && Wrapped)
                    return Finish();
                return true;
            }

            bool Finish()
            {
                int32 Foreground, Motion;
                if (!RasterCounts(RasterA, RasterB, Foreground, Motion))
                    return Fail(TEXT("the live corrected surface has no verified lit raster motion"));
                if (!OutputFile || !OutputFile->Close() || OutputFile->IsError())
                    return Fail(TEXT("could not close the exact corrected native sample stream"));
                auto Record = MakeShared<FJsonObject>();
                Record->SetNumberField(TEXT("schema_version"), 1);
                Record->SetStringField(TEXT("policy"), TEXT("UCC_UNREAL_REGISTERED_PREVIEW_OBSERVATION_V1"));
                Record->SetStringField(TEXT("scene"), PreviewScene);
                Record->SetStringField(TEXT("packet_sha256"), PacketSha);
                Record->SetNumberField(TEXT("native_vertices"), NativeVertices);
                Record->SetNumberField(TEXT("frames"), Frames);
                Record->SetNumberField(TEXT("fps"), Fps);
                Record->SetBoolField(TEXT("corrected_submit_verified"), true);
                Record->SetBoolField(TEXT("normal_loop_wrap_verified"), true);
                Record->SetBoolField(TEXT("lit_motion_verified"), true);
                Record->SetNumberField(TEXT("raster_foreground_pixels"), Foreground);
                Record->SetNumberField(TEXT("raster_changed_pixels"), Motion);
                if (!WriteJson(Output / TEXT("preview-observation.json"), Record))
                    return Fail(TEXT("could not write the owned PIE observation"));
                GEditor->RequestEndPlayMap();
                Finishing = true;
                return true;
            }

            bool Fail(const TCHAR* Message)
            {
                UE_LOG(LogTemp, Error, TEXT("UCC native corrected PIE verification failed: %s"), Message);
                FPlatformMisc::RequestExitWithStatus(false, 1);
                return false;
            }

            FString Output, PacketSha;
            double Deadline;
            TArray<float> Sample;
            TBitArray<> Seen;
            TArray<FColor> RasterA, RasterB;
            TUniquePtr<FArchive> OutputFile;
            int32 PreviousIndex = INDEX_NONE;
            int32 NativeVertices = 0;
            int32 Samples = 0;
            uint64 PreviousSerial = 0;
            bool Requested = false;
            bool Wrapped = false;
            bool Finishing = false;
        };
    }

    void StartPreviewVerifier()
    {
        FString Output;
        if (IsRunningCommandlet() || !FParse::Value(FCommandLine::Get(), TEXT("UccPreviewVerify="), Output))
            return;
        FPaths::NormalizeDirectoryName(Output);
        TArray<FString> Entries;
        IFileManager::Get().FindFiles(Entries, *(Output / TEXT("*")), true, true);
        if (FPaths::IsRelative(Output) || !IFileManager::Get().DirectoryExists(*Output) || !Entries.IsEmpty())
        {
            UE_LOG(LogTemp, Error, TEXT("UCC native corrected PIE needs an existing empty owned output directory"));
            FPlatformMisc::RequestExitWithStatus(false, 1);
            return;
        }
        auto Observer = MakeShared<FPieVerifier>(MoveTemp(Output));
        FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda(
            [Observer](float) { return Observer->Tick(); }));
    }
}
