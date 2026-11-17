// Trusted headless port controls. Linked against the pinned Endless Sky engine.
// GPL-3.0-or-later, consistent with the linked upstream game.
#define SDL_MAIN_HANDLED
#include "Account.h"
#include "Command.h"
#include "Files.h"
#include "GameData.h"
#include "ScreenPlay.h"
#include "HiringPanel.h"
#include "Interface.h"
#include "PlayerInfo.h"
#include "PluginManager.h"
#include "Preferences.h"
#include "Screen.h"
#include "Ship.h"
#include "TaskQueue.h"
#include "TradingPanel.h"
#include <SDL2/SDL.h>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

class TradingControl : public TradingPanel {
public:
    using TradingPanel::TradingPanel;
    using TradingPanel::Click;
};

class HiringControl : public HiringPanel {
public:
    using HiringPanel::HiringPanel;
    using HiringPanel::KeyDown;
};

int main(int argc, char **argv) {
    try {
        SDL_Init(SDL_INIT_EVENTS | SDL_INIT_TIMER);
        SDL_SetModState(KMOD_NONE);
        TaskQueue::SetWorkerThreadCount(2);
        Files::Init(argv);
        Preferences::Load();
        PluginManager::LoadSettings();
        Screen::SetRaw(1100, 720, true);
        PlayerInfo player;
        TaskQueue queue;
        GameData::BeginLoad(queue, player, true, false, true).get();
        GameData::FinishLoading();
        ScreenPlay::Initialize(player);
        TradingControl trading(player);
        HiringControl hiring(player);
        std::string panel = "port";
        int sequence = 0, updates = 0;
        auto publish = [&]() {
            ScreenPlay::Publish(player);
            std::ifstream file(std::getenv("SCREENPLAY_STATE_FILE"));
            std::string state((std::istreambuf_iterator<char>(file)), {});
            const auto end = state.rfind('}');
            if(end == std::string::npos) throw std::runtime_error("Missing native state");
            std::cout << "GWSTATE " << state.substr(0, end)
                << ",\"panel\":" << std::quoted(panel)
                << ",\"required_crew\":" << player.Flagship()->RequiredCrew()
                << ",\"bunks\":" << player.Flagship()->Attributes().Get("bunks") << "}" << std::endl;
        };
        publish();
        std::string line;
        while(std::getline(std::cin, line)) {
            std::istringstream input(line);
            std::string command, argument;
            int advance = 0;
            if(!(input >> command >> advance) || advance < 0 || advance > 15000)
                throw std::runtime_error("Invalid trusted command");
            if(command == "open") {
                input >> argument;
                if(argument != "trading" && argument != "hiring") throw std::runtime_error("Invalid panel");
                panel = argument;
            } else if(command == "close") {
                panel = "port";
            } else if(command == "buy" || command == "sell") {
                if(panel != "trading") throw std::runtime_error("Trading panel is not open");
                input >> std::quoted(argument);
                int index = -1;
                for(size_t i = 0; i < GameData::Commodities().size(); ++i)
                    if(GameData::Commodities()[i].name == argument) index = static_cast<int>(i);
                if(index < 0) throw std::runtime_error("Unknown commodity");
                const Interface *layout = GameData::Interfaces().Get("trade (small screen)");
                Rectangle box = layout->GetBox("content");
                int x = static_cast<int>(box.Left() + layout->GetValue(command == "buy" ? "column: buy" : "column: sell") + 1);
                int y = static_cast<int>(box.Top() + 25 + 20 * index + 1);
                if(!trading.Click(x, y, MouseButton::LEFT, 1)) throw std::runtime_error("Native trading click not handled");
            } else if(command == "hire" || command == "fire") {
                if(panel != "hiring") throw std::runtime_error("Hiring panel is not open");
                // A separately compiled copy omits only the final rendering call.
                // Native Draw computes maxHire/maxFire; native KeyDown changes crew.
                hiring.Draw();
                if(!hiring.KeyDown(command == "hire" ? 'h' : 'f', 0, Command(), true))
                    throw std::runtime_error("Native hiring key not handled");
            } else if(command != "wait") {
                throw std::runtime_error("Unknown trusted command");
            }
            ++sequence;
            updates += advance;
            {
                std::ofstream control(std::getenv("SCREENPLAY_CONTROL_FILE"));
                control << sequence << ' ' << updates << '\n';
            }
            for(int i = 0; i <= advance; ++i) ScreenPlay::BeginFrame();
            publish();
        }
        SDL_Quit();
    } catch(const std::exception &error) {
        std::cerr << "Headless port driver: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
