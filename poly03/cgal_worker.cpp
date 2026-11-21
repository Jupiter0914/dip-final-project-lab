// Binary IPC adapter; simplification and topology tests use upstream CGAL 5.4.
#include <CGAL/Exact_predicates_inexact_constructions_kernel.h>
#include <CGAL/Constrained_Delaunay_triangulation_2.h>
#include <CGAL/Constrained_triangulation_plus_2.h>
#include <CGAL/Polygon_2.h>
#include <CGAL/Polyline_simplification_2/simplify.h>
#include <CGAL/Polyline_simplification_2/Scaled_squared_distance_cost.h>
#include <CGAL/Polyline_simplification_2/Squared_distance_cost.h>
#include <CGAL/Polyline_simplification_2/Stop_below_count_threshold.h>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace PS = CGAL::Polyline_simplification_2;
using K = CGAL::Exact_predicates_inexact_constructions_kernel;
using Vb = PS::Vertex_base_2<K>;
using Fb = CGAL::Constrained_triangulation_face_base_2<K>;
using Tds = CGAL::Triangulation_data_structure_2<Vb, Fb>;
using Cdt = CGAL::Constrained_Delaunay_triangulation_2<K, Tds, CGAL::Exact_predicates_tag>;
using Ct = CGAL::Constrained_triangulation_plus_2<Cdt>;
using Point = K::Point_2;
using Ring = std::vector<Point>;

template<class T> T read_value() {
    T value;
    if (!std::cin.read(reinterpret_cast<char*>(&value), sizeof(value)))
        throw std::runtime_error("Truncated request");
    return value;
}
template<class T> void send(T value) {
    std::cout.write(reinterpret_cast<const char*>(&value), sizeof(value));
}

void simplify_request(std::uint32_t ring_count, std::uint32_t budget, std::uint32_t cost) {
    auto start = std::chrono::steady_clock::now();
    std::vector<Ring> input(ring_count);
    std::size_t total = 0;
    for (Ring& ring : input) {
        std::uint32_t count = read_value<std::uint32_t>();
        ring.reserve(count);
        for (std::uint32_t i=0; i<count; ++i) {
            auto x = read_value<std::int32_t>();
            auto y = read_value<std::int32_t>();
            ring.emplace_back(x, y);
        }
        total += count;
    }

    Ct ct;
    std::vector<Ct::Constraint_id> ids;
    ids.reserve(ring_count);
    for (const auto& ring : input) {
        // The polygon overload inserts its closing segment. Do not insert rings separately into different CDTs.
        CGAL::Polygon_2<K> polygon(ring.begin(), ring.end());
        ids.push_back(ct.insert_constraint(polygon));
    }
    if (ct.number_of_vertices() != total)
        throw std::runtime_error("Intersecting or shared input vertices outside this adapter's domain");
    const auto insert_done = std::chrono::steady_clock::now();
    if (total > budget) {
        const PS::Stop_below_count_threshold stop(budget);
        if (cost == 0) PS::simplify(ct, PS::Squared_distance_cost(), stop);
        else PS::simplify(ct, PS::Scaled_squared_distance_cost(), stop);
    }
    std::vector<Ring> output;
    for (auto id : ids) {
        Ring ring;
        for (auto it=ct.vertices_in_constraint_begin(id); it!=ct.vertices_in_constraint_end(id); ++it)
            ring.push_back((*it)->point());
        if (ring.size()>1 && ring.front() == ring.back()) ring.pop_back();
        output.push_back(std::move(ring));
    }
    const auto end = std::chrono::steady_clock::now();
    send<std::uint32_t>(0);
    send<std::uint32_t>(ring_count);
    send<double>(std::chrono::duration<double,std::milli>(insert_done-start).count());
    send<double>(std::chrono::duration<double,std::milli>(end-start).count());
    for (const Ring& ring : output) {
        send<std::uint32_t>(ring.size());
        for (const Point& point : ring) {
            send<std::int32_t>(std::lround(CGAL::to_double(point.x())));
            send<std::int32_t>(std::lround(CGAL::to_double(point.y())));
        }
    }
}

int main() {
    std::ios_base::sync_with_stdio(false);
    std::cin.tie(nullptr);
    const char ready[] = "CG54";
    std::cout.write(ready,4).flush();
    while (std::cin.peek() != std::char_traits<char>::eof()) {
        try {
            const auto rings = read_value<std::uint32_t>();
            const auto target = read_value<std::uint32_t>();
            const auto cost = read_value<std::uint32_t>();
            if (!rings) return 0;
            simplify_request(rings, target, cost);
        } catch (const std::exception& e) {
            std::string text(e.what());
            send<std::uint32_t>(1);
            send<std::uint32_t>(text.size());
            std::cout.write(text.data(), text.size());
        }
        std::cout.flush();
    }
    return 0;
}
