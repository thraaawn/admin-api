%module pyexmdb
%{
    #include "ExmdbClient.h"
    #include "queries.h"
    #include "structures.h"
%}

%include "std_string.i"
%include "std_except.i"
%include "std_vector.i"
%include "stdint.i"

%template(VI) std::vector<exmdbpp::TaggedPropval>;
%template(VVI) std::vector<std::vector<exmdbpp::TaggedPropval> >;

namespace exmdbpp
{

class ExmdbClient
{
public:
    ExmdbClient(const std::string&, uint16_t, const std::string&, bool) throw (std::runtime_error);
};

struct TaggedPropval
{
    TaggedPropval() = default;
    TaggedPropval(const TaggedPropval&);
    ~TaggedPropval();
    uint32_t tag;
    uint16_t type;
    std::string printValue() const;
    std::string toString() const;
};

template<class Request>
struct Response
{
    Response() = default;
};

struct QueryTableRequest;
struct CreateFolderByPropertiesRequest;

template<>
struct Response<QueryTableRequest>
{
    Response() = default;

    std::vector<std::vector<TaggedPropval> > entries;
};

%nodefaultctor;

template<>
struct Response<CreateFolderByPropertiesRequest>
{
    uint64_t folderId;
};

%clearnodefaultctor;

%template(QueryTableResponse) exmdbpp::Response<exmdbpp::QueryTableRequest>;
%template(CreateFolderByPropertiesResponse) exmdbpp::Response<exmdbpp::CreateFolderByPropertiesRequest>;

namespace queries
{

Response<QueryTableRequest> getFolderList(ExmdbClient&, const std::string&) throw (std::runtime_error);
Response<CreateFolderByPropertiesRequest> createPublicFolder(ExmdbClient&, const std::string&, uint32_t, const std::string&, const std::string&, const std::string&) throw (std::runtime_error);

}

}

