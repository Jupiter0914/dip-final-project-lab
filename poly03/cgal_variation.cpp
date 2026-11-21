// Diagnostic-only build. The production worker and its CGAL headers are untouched.
#define main unused_original_main
#include "cgal_worker.cpp"
#undef main
#include <CGAL/Random.h>
#include <algorithm>
#include <array>
#include <iomanip>
bool poly03_xy_ties = false;

struct TraceStop {
    unsigned target;
    std::vector<std::array<double,4>>* events;
    template<class T,class V,class F>
    bool operator()(T const&, V v, F cost, std::size_t, std::size_t current) const {
        events->push_back({CGAL::to_double(v->point().x()),CGAL::to_double(v->point().y()),
            CGAL::to_double(cost),static_cast<double>(current)});
        return current<=target;
    }
};

int main(int argc,char** argv) {
    if (argc!=5) throw std::runtime_error("Expected cost seed repeats tie_rule");
    const bool scaled=std::string(argv[1])=="scaled";
    const int seed=std::stoi(argv[2]),repeats=std::stoi(argv[3]);
    poly03_xy_ties=std::string(argv[4])=="xy";
    unsigned nr,target;
    std::cin >> nr >> target;
    std::vector<Ring> input(nr);
    unsigned n=0;
    for(auto& ring:input) {
        unsigned k; std::cin>>k; n+=k;
        for(unsigned j=0;j<k;++j) {int x,y;std::cin>>x>>y;ring.emplace_back(x,y);}
    }
    std::cout<<std::setprecision(17);
    for(int attempt=0;attempt<repeats;++attempt) {
        if(seed>=0) CGAL::get_default_random()=CGAL::Random(static_cast<unsigned>(seed));
        Ct ct;
        std::vector<Ct::Constraint_id> ids;
        ids.reserve(nr);
        for(const auto& ring:input) {
            CGAL::Polygon_2<K> p(ring.begin(),ring.end());
            ids.push_back(ct.insert_constraint(p));
        }
        std::cout<<"{\"ring_order\":[";
        unsigned j=0;
        for(auto it=ct.constraints_begin();it!=ct.constraints_end();++it)
            std::cout<<(j++?",":"")<<(std::find(ids.begin(),ids.end(),*it)-ids.begin());
        std::vector<std::array<double,4>> log;
        log.reserve(n+3);
        const TraceStop stop{target,&log};
        if(scaled) PS::simplify(ct,PS::Scaled_squared_distance_cost(),stop);
        else PS::simplify(ct,PS::Squared_distance_cost(),stop);
        std::cout<<"],\"events\":[";
        for(unsigned i=0;i<log.size();++i) {
            auto& p=log[i];
            std::cout<<(i?",":"")<<"["<<p[0]<<","<<p[1]<<","<<p[2]<<","<<p[3]<<"]";
        }
        std::cout<<"],\"rings\":[";
        for(unsigned i=0;i<ids.size();++i) {
            std::cout<<(i?",":"")<<"[";
            auto end=ct.vertices_in_constraint_end(ids[i]); auto last=end; --last;
            bool first=true;
            for(auto it=ct.vertices_in_constraint_begin(ids[i]);it!=last;++it){
                const auto& p=(*it)->point();
                std::cout<<(first?"":",")<<"["<<p.x()<<","<<p.y()<<"]";
                first=false;
            }
            std::cout<<"]";
        }
        std::cout<<"]}\n";
    }
}
