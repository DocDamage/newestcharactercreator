#pragma once

#include "Commandlets/Commandlet.h"
#include "UccNativeAnimationCommandlet.generated.h"

UCLASS()
class UUccNativeAnimationCommandlet final : public UCommandlet
{
    GENERATED_BODY()

public:
    UUccNativeAnimationCommandlet();
    virtual int32 Main(const FString& Params) override;
};
