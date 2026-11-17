#pragma once
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <string>
#include <unistd.h>
namespace gw {
inline bool enabled() { return std::getenv("GAMEWORLD_SESSION") != nullptr; }
inline bool ready=false, loaded=false, won=false, lost=false, advancing=false;
inline int warmup=100;
inline int processed=0, sequence=0, target=0;
inline double x=0, y=0, nativeTime=0;
inline bool next() {
    if (loaded && !ready && --warmup <= 0) ready=true;
    std::ifstream in(std::getenv("GAMEWORLD_CONTROL_FILE"));
    in >> sequence >> target;
    advancing = ready && processed < target;
    if(advancing) ++processed;
    return advancing;
}
inline void publish() {
    std::string file=std::getenv("GAMEWORLD_STATE_FILE"), tmp=file+".tmp";
    double now=std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
    std::ofstream out(tmp); out.precision(16);
    out << "{\"session\":\"" << std::getenv("GAMEWORLD_SESSION") << "\",\"pid\":" << getpid()
        << ",\"captured_at\":" << now << ",\"ready\":" << (ready?"true":"false")
        << ",\"success\":" << (won?"true":"false") << ",\"lost\":" << (lost?"true":"false")
        << ",\"processed_updates\":" << processed << ",\"control_sequence\":" << sequence
        << ",\"frozen\":" << (processed>=target?"true":"false")
        << ",\"native_time\":" << nativeTime << ",\"marble\":[" << x << "," << y << "]}";
    out.close(); std::rename(tmp.c_str(),file.c_str());
}
}
