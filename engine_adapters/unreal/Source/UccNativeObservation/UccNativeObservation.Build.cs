using UnrealBuildTool;
public class UccNativeObservation : ModuleRules
{
    public UccNativeObservation(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.NoPCHs;
        bUseUnity = false;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.AddRange(new[] { "RenderCore", "RHI", "Json", "JsonUtilities", "UnrealEd" });
    }
}
