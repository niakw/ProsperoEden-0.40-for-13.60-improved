#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""R302 upstream-fix source gates and an executable salvage test.

The real shader_cache_reader.inc is compiled in a C++20 host fixture with a
minimal compatible environment. The full source itself, not a rewritten
copy of LoadPipelines, is executed. Native PS5 Vulkan/Mesa builds are separate.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
port = (root/"tools/prepare-vulkan-port.py").read_text()
wsi = (root/"tools/patch-radv-wsi.py").read_text()
cmake = (root/"headless/CMakeLists.txt").read_text()
reader = root/"headless/shader_cache_reader.inc"
checks = (root/"headless/shader_cache_check.cpp").read_text()
host_builder = (root/"tools/build-headless-host.sh").read_text()

# Upstream #102: preserve the 8-512 draw configurable producer cadence,
# but make GPU submission 512 even on non-Android PS5 builds.
assert port.count("static constexpr u32 DRAWS_TO_DISPATCH = 512;") >= 2
assert "'    static constexpr u32 DRAWS_TO_DISPATCH = 512;\\n'" in port
assert "'    const u32 CHECK_MASK = ::Eden::Performance::dispatch_mask.load(std::memory_order_relaxed);\\n\\n'" in port
assert "DRAWS_TO_DISPATCH = 4096;" in port  # pinned *preimage* only
assert "    # From upstream ProsperoEden 0dd9dd0" in port
assert "rasterizer_draw.calls.fetch_add(1" in port  # quiet profile gate preserved
# Upstream #95: one VRR idle period must not be mistaken for a 60 Hz fallback.
assert "if (period > UINT64_C(15000000) && period < UINT64_C(18500000))" in wsi
assert "VIDEOOUT_HIGH_REFRESH_LIMIT_NS" in wsi  # pinned source preimage
# Upstream #72: preserve valid shader-cache prefix on malformed entries.
for term in ("CheckEnvironment(", "kMostShaders = 6", "if (num_envs == 0",
             "std::filesystem::resize_file(", "std::bad_alloc", "std::length_error",
             "if (stop_loading.stop_requested())"):
    assert term in reader.read_text(), term
assert 'list(REMOVE_ITEM video_sources shader_environment.cpp)' in cmake
assert 'list(APPEND video_sources "' in cmake
assert 'shader_cache_reader.inc' in cmake
assert 'add_executable(eden-shader-cache-check' in cmake
assert 'eden-shader-cache-check' in host_builder
assert "an entry cut short" in checks and "a random tail" in checks

fixture = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <functional>
#include <stdexcept>
#include <stop_token>
#include <string>
#include <system_error>
#include <vector>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
#define LOG_ERROR(...) do {} while(0)
#define LOG_INFO(...) do {} while(0)
namespace Common {
template <typename R, typename...Args>
using UniqueFunction=std::function<R(Args...)>;
namespace FS {
bool RemoveFile(const std::filesystem::path& p) {
    return std::filesystem::remove(p);
}
std::string PathToUTF8String(const std::filesystem::path& p) { return p.string(); }
}
}
namespace Shader { enum class Stage { Compute, Vertex }; }
namespace VideoCommon {
constexpr std::array<char,8> MAGIC_NUMBER={'y','u','z','u','c','a','c','h'};
class FileEnvironment {
public:
    void Deserialize(std::ifstream& file) {
        std::array<u64,5> sizes{};
        file.read(reinterpret_cast<char*>(sizes.data()),sizeof(sizes));
        if(sizes[0]>1000000) throw std::length_error("unexpected");
        std::string bytes(static_cast<std::size_t>(sizes[0]), '\0');
        file.read(bytes.data(),bytes.size());
    }
    Shader::Stage ShaderStage() const { return Shader::Stage::Compute; }
};
#include "reader.inc"
}
template <class T>
void Put(std::string& out,T v) {
  out.append(reinterpret_cast<const char*>(&v),sizeof(v));
}
std::string Entry() {
  std::string s;
  Put<u32>(s,1);
  for(int i=0;i<5;++i) Put<u64>(s,i==0?4:0);
  s+="code";
  s+="12345678";
  return s;
}
std::string Header() {
  std::string s="yuzucach";
  Put<u32>(s,7);
  return s;
}
int Run(std::filesystem::path p,std::string data,bool stop=false) {
  {std::ofstream f(p,std::ios::binary|std::ios::trunc);f.write(data.data(),data.size());}
  int loaded=0;
  std::stop_source source;
  if(stop) source.request_stop();
  VideoCommon::LoadPipelines(source.get_token(),p,7,
      [&](std::ifstream& stream,VideoCommon::FileEnvironment) {
        char key[8];stream.read(key,8);++loaded;
      },
      [&](std::ifstream& stream,std::vector<VideoCommon::FileEnvironment>) {
        char key[8];stream.read(key,8);++loaded;
      });
  return loaded;
}
int main(){
 auto p=std::filesystem::temp_directory_path()/ "eden-r302-cache-host-fixture.bin";
 auto e=Entry(),whole=Header()+e+e;
 assert(Run(p,whole)==2 && std::filesystem::file_size(p)==whole.size());
 assert(Run(p,whole+std::string(4096,'\0'))==2 && std::filesystem::file_size(p)==whole.size());
 assert(Run(p,whole+e.substr(0,e.size()/2))==2 && std::filesystem::file_size(p)==whole.size());
 auto corrupt=e;
 std::fill(corrupt.begin()+4,corrupt.begin()+12,'\x7f');
 assert(Run(p,whole+corrupt)==2 && std::filesystem::file_size(p)==whole.size());
 assert(Run(p,whole+std::string(100,'\xa5'))==2 && std::filesystem::file_size(p)==whole.size());
 assert(Run(p,Header()+std::string(200,'\0'))==0 && std::filesystem::file_size(p)==Header().size());
 assert(Run(p,std::string())==0 && !std::filesystem::exists(p));
 assert(Run(p,whole,true)==0 && std::filesystem::file_size(p)==whole.size());
 std::filesystem::remove(p);
 std::puts("PASS: native shader-cache reader preserves whole entries on damaged tails");
}
"""
compiler = next((s for s in ("clang++-18","clang++","g++") if shutil.which(s)),None)
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-r302-fixes-") as tmp:
    temp=Path(tmp)
    # The compiled content is the identical inc that native source generation uses.
    (temp/"reader.inc").write_bytes(reader.read_bytes())
    (temp/"check.cpp").write_text(fixture)
    executable=temp/"check"
    subprocess.run([compiler,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                    "-I",str(temp),str(temp/"check.cpp"),"-o",str(executable)],
                   check=True)
    subprocess.run([str(executable)],check=True,timeout=15)
print("PASS: upstream #102 GPU submit cap, #95 VRR gate, #72 shader cache recovery source contracts")
print("HOST ONLY: native Mesa/PS5 compilation and hardware performance qualification are separate")
