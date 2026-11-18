using UnrealBuildTool;

public class UccNativeAnimation : ModuleRules
{
    public UccNativeAnimation(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.NoPCHs;
        bUseUnity = false;
        PrivateDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Engine", "UnrealEd", "AssetTools", "AssetRegistry",
            "Json", "RenderCore", "RHI", "InterchangeEngine", "UccRegisteredPreview", "ProceduralMeshComponent"
        });
        PublicSystemLibraries.Add("bcrypt.lib");
    }
}
