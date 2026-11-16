#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "UccNativeObservationLibrary.generated.h"
class USkeletalMesh;
/** Private editor observation only: never imports, repairs or saves a mesh. */
UCLASS()
class UCCNATIVEOBSERVATION_API UUccNativeObservationLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="UCC|PrivateObservation")
    static FString ObserveSkeletalMesh(USkeletalMesh* Mesh);
};
