#include "UccNativeAnimationCommandlet.h"
#include "UccNativeAnimation.h"

#include "HAL/FileManager.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, UccNativeAnimation)

UUccNativeAnimationCommandlet::UUccNativeAnimationCommandlet()
{
    IsClient = false;
    IsServer = false;
    IsEditor = true;
    LogToConsole = true;
}

int32 UUccNativeAnimationCommandlet::Main(const FString& Params)
{
    FString Phase, Output, Fbx;
    const bool HasOutput = FParse::Value(*Params, TEXT("UccOutput="), Output);
    FPaths::NormalizeDirectoryName(Output);
    if (!FParse::Value(*Params, TEXT("UccPhase="), Phase) || !HasOutput
        || FPaths::IsRelative(Output) || !IFileManager::Get().DirectoryExists(*Output))
    {
        UE_LOG(LogTemp, Error, TEXT("UCC animation requires Stage or Verify and an existing owned output directory"));
        return 1;
    }
    TArray<FString> Entries;
    IFileManager::Get().FindFiles(Entries, *(Output / TEXT("*")), true, true);
    if (!Entries.IsEmpty())
    {
        UE_LOG(LogTemp, Error, TEXT("UCC animation output directory must be empty"));
        return 1;
    }
    if (Phase == TEXT("Stage") && FParse::Value(*Params, TEXT("UccFbx="), Fbx)
        && !FPaths::IsRelative(Fbx) && FPaths::GetExtension(Fbx).Equals(TEXT("fbx"), ESearchCase::IgnoreCase))
    {
        return UccNativeAnimation::ImportFbx(Fbx, Output) ? 0 : 1;
    }
    if (Phase == TEXT("Verify") && !FParse::Value(*Params, TEXT("UccFbx="), Fbx))
    {
        UccNativeAnimation::FInputs Inputs;
        return UccNativeAnimation::CollectSavedInputs(Inputs)
            && UccNativeAnimation::Observe(Inputs, Output) ? 0 : 1;
    }
    UE_LOG(LogTemp, Error, TEXT("Unsupported UCC animation phase or input"));
    return 1;
}
