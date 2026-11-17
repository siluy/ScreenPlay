#include "GameWorld.h"
#include "Account.h"
#include "CargoHold.h"
#include "DataFile.h"
#include "DataNode.h"
#include <map>
#include <vector>
#include "GameData.h"
#include "PilotProfile.h"
#include "Planet.h"
#include "Outfit.h"
#include <iomanip>
#include "PlayerInfo.h"
#include "Random.h"
#include "Ship.h"
#include "StartConditions.h"
#include "System.h"
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unistd.h>
namespace GameWorld {
namespace {
bool ready=false, advance=false, violation=false, loanViolation=false;
int processed=0, sequence=0, target=0;
std::string scenario;
std::shared_ptr<Ship> originalShip;
std::map<const Outfit *,int> originalOutfits;
std::map<std::string,int> initialCargo, goalCargo, basket;
int initialCrew=1, goalCrew=-1, basketTotal=0;
int64_t initialCredits=30000, minCredits=20000;
const std::vector<std::string> commodities={"Food","Clothing","Metal","Plastic","Equipment","Medical","Industrial","Electronics","Heavy Metals","Luxury Goods"};
}
bool Enabled() { return std::getenv("GAMEWORLD_SESSION") != nullptr; }
bool Ready() { return ready; }
bool Advance() { return advance; }
void Violation() { violation=true; }
void Initialize(PlayerInfo &player) {
    scenario=std::getenv("GAMEWORLD_SCENARIO");
    std::ifstream fixture(std::string(std::getenv("GAMEWORLD_PRIVATE_DIR"))+"/fixture.txt");
    if(!fixture) throw std::runtime_error("Missing private fixture.txt");
    DataFile setup(fixture);
    for(const auto &node:setup) {
        const auto &key=node.Token(0);
        if(key=="credits") initialCredits=node.Value(1);
        else if(key=="mincash") minCredits=node.Value(1);
        else if(key=="crew") initialCrew=node.Value(1);
        else if(key=="goalcrew") goalCrew=node.Value(1);
        else if(key=="cargo") initialCargo[node.Token(1)]=node.Value(2);
        else if(key=="goal") goalCargo[node.Token(1)]=node.Value(2);
        else if(key=="basket") basket[node.Token(1)]=node.Value(2);
        else if(key=="baskettotal") basketTotal=node.Value(1);
        else throw std::runtime_error("Unknown fixture token");
    }
    Random::SetFixedSeed(20260914);
    std::ostringstream startText;
    startText << 
        "start GameWorld\n\tname GameWorld\n\tsystem Rutilicus\n\tplanet \"New Boston\"\n"
        "\tdate 16 11 3013\n\tconversation \"default intro\"\n"
        "\tship Shuttle \"GameWorld Courier\"\n\taccount\n\t\tcredits " << initialCredits << "\n"
        "\tset \"license: Pilot's\"\n\tset \"species: human\"\n";
    std::istringstream input(startText.str());
    DataFile file(input);
    StartConditions start(*file.begin(), &GameData::GlobalConditions(), &player.Conditions());
    start.FinishLoading();
    if(!start.IsValid()) throw std::runtime_error("GameWorld start is invalid");
    auto pilot=PilotProfile::NewProfile();
    pilot->New(GameData::GetGamerules());
    player.New(start,pilot);
    player.SetName("GameWorld","Courier");
    if(player.Ships().size()!=1) throw std::runtime_error("Expected one original Shuttle");
    originalShip=player.Ships().front();
    originalOutfits=originalShip->Outfits();
    // Starting cargo, when requested, uses the normal cargo implementation.
    player.Cargo().SetSize(20);
    for(const auto &[name,amount]:initialCargo)
        if(player.Cargo().Add(name,amount)!=amount) throw std::runtime_error("Invalid initial cargo capacity");
    originalShip->AddCrew(initialCrew-originalShip->Crew());
    if(originalShip->Crew()!=initialCrew) throw std::runtime_error("Invalid crew fixture");
    ready=true; advance=true;
}
void BeginFrame() {
    if(!Enabled() || !ready) return;
    std::ifstream in(std::getenv("GAMEWORLD_CONTROL_FILE"));
    in >> sequence >> target;
    advance=processed<target;
    if(advance) ++processed;
}
void Publish(const PlayerInfo &player) {
    if(!Enabled() || !ready) return;
    int food=player.Cargo().Get("Food"), metal=player.Cargo().Get("Metal"), clothing=player.Cargo().Get("Clothing");
    loanViolation = loanViolation || player.Accounts().TotalDebt() > 0;
    bool shipKept=player.Ships().size()==1 && player.Ships().front()==originalShip && !originalShip->IsDestroyed();
    bool onPlanet=player.GetPlanet() && player.GetPlanet()->TrueName()=="New Boston";
    bool manifest=true;
    int expectedTotal=0, actualBasket=0;
    for(const auto &[name,amount]:goalCargo) { manifest &= player.Cargo().Get(name)==amount; expectedTotal+=amount; }
    for(const auto &[name,minimum]:basket) { const int amount=player.Cargo().Get(name); manifest &= amount>=minimum; actualBasket+=amount; }
    manifest &= actualBasket==basketTotal && player.Cargo().CommoditiesSize()==expectedTotal+basketTotal;
    const bool outfitsKept=originalShip->Outfits()==originalOutfits;
    bool success=manifest && outfitsKept && onPlanet && (goalCrew<0 || originalShip->Crew()==goalCrew)
        && player.Accounts().Credits()>=minCredits && !loanViolation && shipKept && !violation;
    double now=std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
    std::string path=std::getenv("GAMEWORLD_STATE_FILE"), tmp=path+".tmp";
    std::ofstream out(tmp); out.precision(16);
    out << "{\"session\":\"" << std::getenv("GAMEWORLD_SESSION") << "\",\"pid\":" << getpid()
        << ",\"captured_at\":" << now << ",\"ready\":true,\"success\":" << (success?"true":"false")
        << ",\"violations\":" << (violation?"[\"forbidden_game_switch\"]":(loanViolation?"[\"loan_taken\"]":"[]"))
        << ",\"processed_updates\":" << processed << ",\"control_sequence\":" << sequence
        << ",\"frozen\":" << (processed>=target?"true":"false")
        << ",\"food\":" << food << ",\"metal\":" << metal << ",\"clothing\":" << clothing
        << ",\"cash\":" << player.Accounts().Credits() << ",\"debt\":" << player.Accounts().TotalDebt()
        << ",\"ship_kept\":" << (shipKept?"true":"false") << ",\"on_start_planet\":" << (onPlanet?"true":"false")
        << ",\"lost\":" << (player.IsDead()?"true":"false") << "}";
    out.seekp(-1,std::ios_base::cur);
    out << ",\"crew\":" << originalShip->Crew() << ",\"cargo\":{";
    bool first=true;
    for(const auto &name:commodities) { if(!first) out << ","; first=false; out << "\"" << name << "\":" << player.Cargo().Get(name); }
    out << "},\"prices\":{";
    first=true;
    for(const auto &name:commodities) { if(!first) out << ","; first=false; out << "\"" << name << "\":" << player.GetSystem()->Trade(name); }
    out << "},\"cargo_capacity\":" << player.Cargo().Size() << ",\"outfits_kept\":" << (outfitsKept?"true":"false");
    out << ",\"original_outfits\":{"; first=true;
    for(const auto &[outfit,count]:originalOutfits) { if(!first) out << ","; first=false; out << std::quoted(outfit->TrueName()) << ":" << count; }
    out << "},\"installed_outfits\":{"; first=true;
    for(const auto &[outfit,count]:originalShip->Outfits()) { if(!first) out << ","; first=false; out << std::quoted(outfit->TrueName()) << ":" << count; }
    out << "}}";
    out.close(); std::rename(tmp.c_str(),path.c_str());
}
}
