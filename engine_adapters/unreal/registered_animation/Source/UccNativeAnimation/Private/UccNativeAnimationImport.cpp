#include "UccNativeAnimation.h"

#include "Animation/AnimBoneCompressionSettings.h"
#include "Animation/AnimCompress_LeastDestructive.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetCompilingManager.h"
#include "AssetImportTask.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetToolsModule.h"
#include "Dom/JsonObject.h"
#include "Engine/SkeletalMesh.h"
#include "Factories/FbxAnimSequenceImportData.h"
#include "Factories/FbxFactory.h"
#include "Factories/FbxImportUI.h"
#include "Factories/FbxSkeletalMeshImportData.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Modules/ModuleManager.h"
#include "Serialization/JsonSerializer.h"
#include "SkeletalMeshTypes.h"
#include "UObject/SavePackage.h"
#include "UObject/UnrealType.h"

namespace UccNativeAnimation
{
    namespace
    {
        constexpr TCHAR AssetPath[] = TEXT("/Game/UccAnimation");

        TArray<FAssetData> FindAssets(bool ScanDisk)
        {
            auto& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
            if (ScanDisk)
            {
                Registry.ScanPathsSynchronous({AssetPath}, true);
            }
            TArray<FAssetData> Assets;
            Registry.GetAssetsByPath(FName(AssetPath), Assets, true, ScanDisk);
            return Assets;
        }

        bool Collect(const TArray<FAssetData>& Assets, FInputs& Inputs)
        {
            if (Assets.Num() != 3)
            {
                UE_LOG(LogTemp, Error, TEXT("Expected one imported skeletal mesh, skeleton and animation, found %d assets"), Assets.Num());
                return false;
            }
            for (const FAssetData& Row : Assets)
            {
                UObject* Asset = Row.GetAsset();
                if (auto* Mesh = Cast<USkeletalMesh>(Asset); Mesh && !Inputs.Mesh)
                    Inputs.Mesh = Mesh;
                else if (auto* Skeleton = Cast<USkeleton>(Asset); Skeleton && !Inputs.Skeleton)
                    Inputs.Skeleton = Skeleton;
                else if (auto* Clip = Cast<UAnimSequence>(Asset); Clip && !Inputs.Clip)
                    Inputs.Clip = Clip;
                else
                    return false;
            }
            return Inputs.Mesh && Inputs.Skeleton && Inputs.Clip
                && Inputs.Mesh->GetSkeleton() == Inputs.Skeleton && Inputs.Clip->GetSkeleton() == Inputs.Skeleton;
        }

        bool ConfigureLod0(USkeletalMesh& Mesh)
        {
            FSkeletalMeshLODInfo* Lod = Mesh.GetLODInfo(0);
            if (!Lod || Mesh.GetLODNum() != 1)
                return false;
            FScopedSkeletalMeshPostEditChange Change(&Mesh);
            FSkeletalMeshBuildSettings& Build = Lod->BuildSettings;
            Build.bRecomputeNormals = false;
            Build.bRecomputeTangents = true;
            Build.bComputeWeightedNormals = false;
            Build.bUseMikkTSpace = true;
            Build.bRemoveDegenerates = false;
            Build.bUseHighPrecisionTangentBasis = true;
            Build.bUseHighPrecisionSkinWeights = true;
            Build.bUseFullPrecisionUVs = true;
            Build.bUseBackwardsCompatibleF16TruncUVs = false;
            Build.bOptimizeForInstancing = false;
            Build.ThresholdPosition = 0.0f;
            Build.ThresholdTangentNormal = 0.0f;
            Build.ThresholdUV = 0.0f;
            Build.MorphThresholdPosition = 0.0f;
            Build.BoneInfluenceLimit = 0;
            return true;
        }

        bool ConfigureExactCompression(UAnimSequence& Clip)
        {
            Clip.WaitOnExistingCompression();
            auto* Settings = NewObject<UAnimBoneCompressionSettings>(&Clip, TEXT("UccFramePreserving"));
            Settings->Codecs = {NewObject<UAnimCompress_LeastDestructive>(Settings, TEXT("LeastDestructive"))};
            Clip.BoneCompressionSettings = Settings;
            Clip.bAllowFrameStripping = false;
            Clip.bDoNotOverrideCompression = true;
            FPropertyChangedEvent Change(FindFProperty<FProperty>(UAnimSequence::StaticClass(),
                GET_MEMBER_NAME_CHECKED(UAnimSequence, BoneCompressionSettings)));
            Clip.PostEditChangeProperty(Change);
            Clip.CacheDerivedDataForCurrentPlatform();
            return UsesExactCompression(Clip);
        }

        bool SaveAsset(UObject* Asset)
        {
            UPackage* Package = Asset->GetOutermost();
            const FString Target = FPackageName::LongPackageNameToFilename(Package->GetName(),
                FPackageName::GetAssetPackageExtension());
            FSavePackageArgs Args;
            Args.TopLevelFlags = RF_Public | RF_Standalone;
            return !IFileManager::Get().FileExists(*Target) && UPackage::SavePackage(Package, Asset, *Target, Args);
        }
    }

    bool WriteJson(const FString& Path, const TSharedRef<FJsonObject>& Value)
    {
        FString Text;
        return FJsonSerializer::Serialize(Value, TJsonWriterFactory<>::Create(&Text))
            && FFileHelper::SaveStringToFile(Text, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,
                                            &IFileManager::Get(), FILEWRITE_NoReplaceExisting);
    }

    bool UsesExactCompression(const UAnimSequence& Clip)
    {
        const UAnimBoneCompressionSettings* Settings = Clip.BoneCompressionSettings;
        return Settings && Settings->GetOuter() == &Clip && Settings->Codecs.Num() == 1
            && Settings->Codecs[0] && Settings->Codecs[0]->GetOuter() == Settings
            && Settings->Codecs[0]->GetClass() == UAnimCompress_LeastDestructive::StaticClass()
            && !Clip.bAllowFrameStripping && Clip.bDoNotOverrideCompression && Clip.IsBoneCompressedDataValid()
            && Clip.GetCompressedData().Get().BoneCompressionCodec == Settings->Codecs[0];
    }

    bool CollectSavedInputs(FInputs& Inputs)
    {
        return Collect(FindAssets(true), Inputs);
    }

    bool ImportFbx(const FString& FbxPath, const FString& Output)
    {
        if (!IFileManager::Get().FileExists(*FbxPath) || !FindAssets(true).IsEmpty())
        {
            UE_LOG(LogTemp, Error, TEXT("Animated FBX source is missing or project already contains animation assets"));
            return false;
        }

        UFbxImportUI* Options = NewObject<UFbxImportUI>();
        Options->bAutomatedImportShouldDetectType = false;
        Options->MeshTypeToImport = FBXIT_SkeletalMesh;
        Options->OriginalImportType = FBXIT_SkeletalMesh;
        Options->bImportAsSkeletal = true;
        Options->bImportMesh = true;
        Options->bImportAnimations = true;
        Options->bCreatePhysicsAsset = false;
        Options->bImportTextures = false;
        Options->bImportMaterials = false;
        Options->bOverrideFullName = true;
        Options->Skeleton = nullptr;
        auto& MeshOptions = *Options->SkeletalMeshImportData;
        MeshOptions.bImportMorphTargets = true;
        MeshOptions.bImportMeshLODs = false;
        MeshOptions.bImportMeshesInBoneHierarchy = false;
        MeshOptions.bUseT0AsRefPose = false;
        MeshOptions.bUpdateSkeletonReferencePose = false;
        MeshOptions.bConvertScene = true;
        MeshOptions.bConvertSceneUnit = true;
        MeshOptions.bForceFrontXAxis = true;
        MeshOptions.CoordinateSystemPolicy = ECoordinateSystemPolicy::MatchUpForwardAxes;
        MeshOptions.NormalImportMethod = FBXNIM_ImportNormals;
        MeshOptions.NormalGenerationMethod = EFBXNormalGenerationMethod::MikkTSpace;
        MeshOptions.bComputeWeightedNormals = false;
        MeshOptions.ThresholdPosition = 0.0f;
        MeshOptions.ThresholdTangentNormal = 0.0f;
        MeshOptions.ThresholdUV = 0.0f;
        MeshOptions.MorphThresholdPosition = 0.0f;
        Options->AnimSequenceImportData->bConvertScene = true;
        Options->AnimSequenceImportData->bConvertSceneUnit = true;
        Options->AnimSequenceImportData->bForceFrontXAxis = true;
        Options->AnimSequenceImportData->CoordinateSystemPolicy = ECoordinateSystemPolicy::MatchUpForwardAxes;
        Options->AnimSequenceImportData->AnimationLength = FBXALIT_ExportedTime;
        Options->AnimSequenceImportData->bUseDefaultSampleRate = false;
        Options->AnimSequenceImportData->CustomSampleRate = Fps;
        Options->AnimSequenceImportData->bImportBoneTracks = true;
        Options->AnimSequenceImportData->bImportCustomAttribute = false;
        Options->AnimSequenceImportData->bPreserveLocalTransform = false;

        UAssetImportTask* Task = NewObject<UAssetImportTask>();
        Task->Filename = FbxPath;
        Task->DestinationPath = AssetPath;
        Task->DestinationName = TEXT("Character");
        Task->bAutomated = true;
        Task->bReplaceExisting = false;
        Task->bSave = false;
        Task->bAsync = false;
        Task->Factory = NewObject<UFbxFactory>();
        Task->Options = Options;
        FAssetToolsModule::GetModule().Get().ImportAssetTasks({Task});
        if (Task->GetObjects().IsEmpty())
        {
            UE_LOG(LogTemp, Error, TEXT("Unreal legacy FBX import returned no objects"));
            return false;
        }
        FAssetCompilingManager::Get().FinishAllCompilation();

        FInputs Inputs;
        if (!Collect(FindAssets(false), Inputs) || !ConfigureLod0(*Inputs.Mesh))
        {
            UE_LOG(LogTemp, Error, TEXT("Could not configure the imported animation and skeletal LOD0"));
            return false;
        }
        FAssetCompilingManager::Get().FinishAllCompilation();
        if (!ConfigureExactCompression(*Inputs.Clip)
            || !SaveAsset(Inputs.Skeleton) || !SaveAsset(Inputs.Mesh) || !SaveAsset(Inputs.Clip))
        {
            UE_LOG(LogTemp, Error, TEXT("Could not save the exact imported animation asset closure"));
            return false;
        }
        auto Report = MakeShared<FJsonObject>();
        Report->SetNumberField(TEXT("schema_version"), 1);
        Report->SetStringField(TEXT("policy"), TEXT("UCC_UNREAL_NATIVE_ANIMATION_STAGE_V1"));
        Report->SetStringField(TEXT("mesh"), Inputs.Mesh->GetPathName());
        Report->SetStringField(TEXT("skeleton"), Inputs.Skeleton->GetPathName());
        Report->SetStringField(TEXT("clip"), Inputs.Clip->GetPathName());
        return WriteJson(Output / TEXT("import.json"), Report);
    }
}
