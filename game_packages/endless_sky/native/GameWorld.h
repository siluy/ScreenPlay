#pragma once
class PlayerInfo;
namespace GameWorld {
bool Enabled();
bool Ready();
bool Advance();
void Initialize(PlayerInfo &player);
void BeginFrame();
void Publish(const PlayerInfo &player);
void Violation();
}
