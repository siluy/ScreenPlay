/* ScreenPlay development integration. GPL-2.0, matching OpenTTD.
 * Initialization and state export are trusted harness operations, never agent tools.
 * Agent actions still pass through the original desktop UI and native commands.
 */
#include "stdafx.h"
#include "screenplay_bridge.h"
#include "openttd.h"
#include "command_func.h"
#include "company_base.h"
#include "company_func.h"
#include "town_cmd.h"
#include "road_cmd.h"
#include "road_map.h"
#include "station_cmd.h"
#include "station_map.h"
#include "station_base.h"
#include "newgrf_roadstop.h"
#include "vehicle_cmd.h"
#include "vehicle_base.h"
#include "vehicle_gui.h"
#include "roadveh.h"
#include "order_cmd.h"
#include "engine_base.h"
#include "engine_func.h"
#include "cargotype.h"
#include "signs_cmd.h"
#include "viewport_func.h"
#include "gfx_func.h"
#include "settings_type.h"
#include "timer/timer_game_tick.h"
#include "3rdparty/nlohmann/json.hpp"
#include <fstream>
#include <filesystem>
#include <chrono>
#include <unistd.h>

namespace {
bool ready = false, pending = false, reset_violation = false;
std::string error;
uint64_t updates = 0, target_updates = 0, control_sequence = 0, state_sequence = 0;
VehicleID bus_id = VehicleID::Invalid();
StationID west = StationID::Invalid(), east = StationID::Invalid();
bool visited_west = false, visited_east = false;
int64_t min_cash = 50000;
bool loan_violation = false;
std::vector<uint> gap_x;
nlohmann::json fixture;
std::vector<std::pair<TileIndex,RoadBits>> repairs;
StationID central=StationID::Invalid();
bool visited_central=false;


void Require(const CommandCost &cost, const char *operation) {
    if (cost.Failed()) throw std::runtime_error(fmt::format("{} failed (error {})", operation, cost.GetErrorMessage()));
}

void Initialize() {
    if (ready) { reset_violation = true; return; }
    const std::string scenario = getenv("SCREENPLAY_SCENARIO") ? getenv("SCREENPLAY_SCENARIO") : "";
    std::ifstream input(std::string(getenv("SCREENPLAY_PRIVATE_DIR"))+"/fixture.json");
    nlohmann::json parameters; input >> parameters;
    fixture=parameters.at("fixture");
    gap_x=fixture.value("gaps",std::vector<uint>{});

    _current_company = OWNER_DEITY;
    auto town = Command<CMD_FOUND_TOWN>::Do(DoCommandFlag::Execute, TileXY(24, 14), TSZ_SMALL,
        false, TL_ORIGINAL, false, 0, std::string("ScreenPlay Town"));
    Require(std::get<0>(town), "create town");
    _current_company = _local_company;
    SetLocalCompany(CompanyID::Begin());
    _current_company = _local_company;
    Company *company = Company::Get(_local_company);
    company->money = 1000000;
    for (uint x = 16; x <= 34; ++x) {
        if (fixture.value("detour",false) && x>=22 && x<=28) continue;
        if (std::find(gap_x.begin(), gap_x.end(), x) != gap_x.end()) { repairs.emplace_back(TileXY(x,32),ROAD_X); continue; }
        RoadBits bits = x == 16 ? RoadBits(ROAD_X | ROAD_SE) : ROAD_X;
        Require(Command<CMD_BUILD_ROAD>::Do(DoCommandFlag::Execute, TileXY(x, 32), bits,
            ROADTYPE_ROAD, DRD_NONE, TownID::Invalid()), "build fixture road");
    }
    if(fixture.value("detour",false)) {
        for(uint y=32;y<=36;++y) for(uint x:{21u,29u}) {
            RoadBits bits=ROAD_Y;
            if(y==32) bits=RoadBits(ROAD_Y|ROAD_X);
            if(y==36) bits=RoadBits(ROAD_Y|ROAD_X);
            if(y==34 && x==29) { repairs.emplace_back(TileXY(x,y),ROAD_Y); continue; }
            Require(Command<CMD_BUILD_ROAD>::Do(DoCommandFlag::Execute,TileXY(x,y),bits,ROADTYPE_ROAD,DRD_NONE,TownID::Invalid()),"detour vertical");
        }
        for(uint x=22;x<=28;++x) Require(Command<CMD_BUILD_ROAD>::Do(DoCommandFlag::Execute,TileXY(x,36),ROAD_X,ROADTYPE_ROAD,DRD_NONE,TownID::Invalid()),"detour horizontal");
    }
    const TileIndex depot = TileXY(16, 33);
    Require(Command<CMD_BUILD_ROAD_DEPOT>::Do(DoCommandFlag::Execute, depot, ROADTYPE_ROAD, DIAGDIR_NW), "build depot");
    for (uint x : {18u, 32u}) {
        Require(Command<CMD_BUILD_ROAD_STOP>::Do(DoCommandFlag::Execute, TileXY(x, 32), 1, 1,
            RoadStopType::Bus, true, DIAGDIR_NE, ROADTYPE_ROAD, ROADSTOP_CLASS_DFLT, 0,
            StationID::Invalid(), true), "build bus stop");
    }
    west = GetStationIndex(TileXY(18, 32));
    east = GetStationIndex(TileXY(32, 32));
    Require(Command<CMD_RENAME_STATION>::Do(DoCommandFlag::Execute, west, std::string("West Stop")), "name west stop");
    Require(Command<CMD_RENAME_STATION>::Do(DoCommandFlag::Execute, east, std::string("East Stop")), "name east stop");
    if(fixture.value("central",false)) {
        const TileIndex tile=TileXY(25,fixture.value("detour",false)?36:32);
        Require(Command<CMD_BUILD_ROAD_STOP>::Do(DoCommandFlag::Execute,tile,1,1,RoadStopType::Bus,true,DIAGDIR_NE,ROADTYPE_ROAD,ROADSTOP_CLASS_DFLT,0,StationID::Invalid(),true),"central stop");
        central=GetStationIndex(tile);
        Require(Command<CMD_RENAME_STATION>::Do(DoCommandFlag::Execute,central,std::string("Central Stop")),"name central");
    }
    EngineID bus_engine = EngineID::Invalid();
    for (const Engine *e : Engine::Iterate()) {
        if (e->type == VEH_ROAD && e->GetDefaultCargoType() == GetCargoTypeByLabel(CT_PASSENGERS)
            && IsEngineBuildable(e->index, VEH_ROAD, _local_company)) {
            bus_engine = e->index; break;
        }
    }
    if (bus_engine == EngineID::Invalid()) throw std::runtime_error("No buildable bus at fixture date");
    auto vehicle = Command<CMD_BUILD_VEHICLE>::Do(DoCommandFlag::Execute, depot, bus_engine,
        true, INVALID_CARGO, INVALID_CLIENT_ID);
    Require(std::get<0>(vehicle), "build bus");
    bus_id = std::get<1>(vehicle);
    Require(Command<CMD_RENAME_VEHICLE>::Do(DoCommandFlag::Execute, bus_id, std::string("Inspection Bus")), "name bus");
    int orderIndex=0;
    for(const std::string &name:fixture.at("orders")) {
        Order order;
        order.MakeGoToStation(name=="west"?west:(name=="central"?central:east));
        order.SetStopLocation(OrderStopLocation::FarEnd);
        if(fixture.value("full_load",false) && name=="west") order.SetLoadType(OrderLoadType::FullLoadAny);
        Require(Command<CMD_INSERT_ORDER>::Do(DoCommandFlag::Execute,bus_id,orderIndex++,order),"fixture order");
    }
    for(const auto &[tile,bits]:repairs) {
        auto sign=Command<CMD_PLACE_SIGN>::Do(DoCommandFlag::Execute,tile,std::string("Repair road"));
        Require(std::get<0>(sign),"repair marker");
    }
    company->money = 50000;
    company->current_loan = 0;
    min_cash = 50000;
    ScrollMainWindowToTile(TileXY(25, 32), true);
    ShowVehicleViewWindow(Vehicle::Get(bus_id));
    MarkWholeScreenDirty();
    ready = true;
}
}

bool ScreenPlayEnabled() { return getenv("SCREENPLAY_SESSION") != nullptr; }

bool ScreenPlayRejectModeSwitch() {
    if (!ScreenPlayEnabled() || !ready) return false;
    reset_violation = true;
    return true;
}

void ScreenPlayNewGame() {
    if (!ScreenPlayEnabled()) return;
    if (ready) reset_violation = true;
    pending = true;
}

bool ScreenPlayAllowUpdate() {
    if (!ScreenPlayEnabled() || _game_mode != GM_NORMAL) return true;
    if (pending) {
        pending = false;
        try { Initialize(); }
        catch (const std::exception &e) { error = e.what(); }
        _current_company = _local_company;
    }
    if (!ready || !error.empty()) return false;
    const char *path = getenv("SCREENPLAY_CONTROL_FILE");
    if (path) {
        std::ifstream input(path);
        uint64_t sequence, target;
        if ((input >> sequence >> target) && sequence > control_sequence) {
            control_sequence = sequence;
            target_updates = std::min(target, updates + 10000);
        }
    }
    if (updates >= target_updates) return false;
    ++updates;
    return true;
}

void ScreenPlayPublish() {
    if (!ScreenPlayEnabled() || _game_mode != GM_NORMAL) return;
    const char *path = getenv("SCREENPLAY_STATE_FILE");
    if (!path) return;
    nlohmann::json j;
    j["schema_version"] = "0.1";
    j["session"] = getenv("SCREENPLAY_SESSION");
    j["pid"] = getpid();
    j["scenario"] = getenv("SCREENPLAY_SCENARIO") ? getenv("SCREENPLAY_SCENARIO") : "";
    j["ready"] = ready && error.empty();
    j["error"] = error;
    j["state_sequence"] = ++state_sequence;
    j["processed_updates"] = updates;
    j["requested_updates"] = target_updates;
    j["control_sequence"] = control_sequence;
    j["native_tick"] = TimerGameTick::counter;
    j["frozen"] = updates >= target_updates;
    j["captured_at"] = std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
    j["reset_violation"] = reset_violation;
    if (ready) {
        const Company *c = Company::GetIfValid(CompanyID::Begin());
        const Vehicle *v = Vehicle::GetIfValid(bus_id);
        j["company_present"] = c != nullptr;
        j["bus_present"] = v != nullptr;
        if (c) {
            const int64_t cash = c->money;
            min_cash = std::min(min_cash, cash);
            loan_violation |= c->current_loan > 0;
            j["cash"] = cash;
            j["min_cash"] = min_cash;
            j["loan_violation"] = loan_violation;
        }
        if (v) {
            visited_west |= v->last_station_visited == west;
            visited_east |= v->last_station_visited == east;
            visited_central |= central!=StationID::Invalid() && v->last_station_visited==central;
            j["in_depot"]=v->IsInDepot();
            bool normal=true;
            nlohmann::json orderNames=nlohmann::json::array(), implicitNames=nlohmann::json::array();
            for(int i=0;i<v->GetNumOrders();++i) {
                const Order *o=v->GetOrder(i);
                if(o->IsType(OT_IMPLICIT)) {
                    const auto dest=o->GetDestination();
                    implicitNames.push_back(dest==west.base()?"west":(dest==east.base()?"east":(dest==central.base()?"central":"other")));
                    continue;
                }
                if(!o->IsType(OT_GOTO_STATION)) { orderNames.push_back("other"); continue; }
                const auto dest=o->GetDestination();
                orderNames.push_back(dest==west.base()?"west":(dest==east.base()?"east":(dest==central.base()?"central":"other")));
                normal &= o->GetLoadType()==OrderLoadType::LoadIfPossible;
            }
            j["orders"]=orderNames;
            j["implicit_orders"]=implicitNames;
            j["normal_loading"]=normal;
            j["bus"] = {{"id", bus_id.base()}, {"x", TileX(v->tile)}, {"y", TileY(v->tile)},
                {"stopped", v->vehstatus.Test(VehState::Stopped)}, {"crashed", v->vehstatus.Test(VehState::Crashed)},
                {"current_order", v->cur_real_order_index}, {"last_station", v->last_station_visited.base()}};
        }
        uint missing = 0;
        for (const auto &[tile,bits] : repairs) {
            if ((GetAnyRoadBits(tile, RTT_ROAD) & bits) != bits) ++missing;
        }
        j["missing_road_sections"] = missing;
        j["visited_west"] = visited_west;
        j["visited_east"] = visited_east;
        j["visited_central"]=visited_central;
        j["stations_present"] = Station::IsValidID(west) && Station::IsValidID(east) && (central==StationID::Invalid() || Station::IsValidID(central));
        j["map_size"] = {Map::SizeX(), Map::SizeY()};
    }
    try {
        const std::string temporary = std::string(path) + ".tmp";
        { std::ofstream file(temporary); file << j.dump(); }
        std::filesystem::rename(temporary, path);
    } catch (const std::exception &) { /* Runner reports missing/stale telemetry. */ }
}
