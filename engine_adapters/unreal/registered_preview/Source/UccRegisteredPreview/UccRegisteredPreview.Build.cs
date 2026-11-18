using UnrealBuildTool;

public class UccRegisteredPreview : ModuleRules
{
    public UccRegisteredPreview(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.NoPCHs;
        bUseUnity = false;
        CppStandard = CppStandardVersion.Cpp20;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.Add("ProceduralMeshComponent");
    }
}
