//+------------------------------------------------------------------+
//| JAson.mqh — Lightweight JSON parser for MQL5                      |
//| Simplified CJAVal class for reading/writing JSON files.           |
//| Based on the public-domain MQL5 JSON library.                     |
//+------------------------------------------------------------------+
#property copyright "TradingGuard"
#property version   "1.00"

#include <Object.mqh>

//+------------------------------------------------------------------+
enum EJSONTYPE { jtUNDEF, jtNULL, jtBOOL, jtINT, jtDBL, jtSTR, jtARRAY, jtOBJ };

//+------------------------------------------------------------------+
class CJAVal : public CObject
{
public:
    EJSONTYPE   m_type;
    bool        m_bv;     // bool value
    long        m_iv;     // int value
    double      m_dv;     // double value
    string      m_sv;     // string value
    string      m_key;    // key name
    CJAVal      *m_parent;
    CJAVal      *m_children[];

    // ── Constructor / Destructor ─────────────────────────────────────
    CJAVal() : m_type(jtUNDEF), m_bv(false), m_iv(0), m_dv(0.0),
               m_sv(""), m_key(""), m_parent(NULL) {}

    CJAVal(EJSONTYPE t, string val = "") : m_type(t), m_bv(false),
        m_iv(0), m_dv(0.0), m_sv(val), m_key(""), m_parent(NULL) {}

    ~CJAVal()
    {
        Clear();
    }

    // ── Clear all children ───────────────────────────────────────────
    void Clear()
    {
        for (int i = ArraySize(m_children) - 1; i >= 0; i--)
        {
            if (m_children[i] != NULL)
            {
                delete m_children[i];
                m_children[i] = NULL;
            }
        }
        ArrayResize(m_children, 0);
    }

    // ── Size ─────────────────────────────────────────────────────────
    int Size() { return ArraySize(m_children); }

    // ── Access by key (creates if missing) ───────────────────────────
    CJAVal *operator[](string key)
    {
        for (int i = 0; i < ArraySize(m_children); i++)
            if (m_children[i].m_key == key)
                return m_children[i];
        // Create new child
        CJAVal *child = new CJAVal();
        child.m_key = key;
        child.m_parent = GetPointer(this);
        int sz = ArraySize(m_children);
        ArrayResize(m_children, sz + 1);
        m_children[sz] = child;
        return child;
    }

    // ── Access by index ──────────────────────────────────────────────
    CJAVal *operator[](int idx)
    {
        if (idx < 0 || idx >= ArraySize(m_children))
            return NULL;
        return m_children[idx];
    }

    // ── Value getters ────────────────────────────────────────────────
    bool   IsNull()     { return m_type == jtNULL || m_type == jtUNDEF; }
    bool   IsObject()   { return m_type == jtOBJ; }
    bool   IsArray()    { return m_type == jtARRAY; }
    bool   IsString()   { return m_type == jtSTR; }
    bool   IsNumber()   { return m_type == jtINT || m_type == jtDBL; }
    bool   IsBool()     { return m_type == jtBOOL; }

    bool   GetBool()    { return m_bv; }
    long   GetInt()     { return m_iv; }
    double GetDbl()     { return m_dv; }
    string GetStr()     { return m_sv; }

    double ToDouble()
    {
        if (m_type == jtDBL) return m_dv;
        if (m_type == jtINT) return (double)m_iv;
        if (m_type == jtSTR) return StringToDouble(m_sv);
        return 0.0;
    }

    long ToInt()
    {
        if (m_type == jtINT) return m_iv;
        if (m_type == jtDBL) return (long)m_dv;
        if (m_type == jtSTR) return StringToInteger(m_sv);
        return 0;
    }

    bool ToBool()
    {
        if (m_type == jtBOOL) return m_bv;
        if (m_type == jtINT)  return m_iv != 0;
        if (m_type == jtSTR)  return m_sv == "true";
        return false;
    }

    string ToString()
    {
        if (m_type == jtSTR)  return m_sv;
        if (m_type == jtBOOL) return m_bv ? "true" : "false";
        if (m_type == jtINT)  return IntegerToString(m_iv);
        if (m_type == jtDBL)  return DoubleToString(m_dv, 8);
        return "";
    }

    // ── Setters ──────────────────────────────────────────────────────
    void Set(bool v)   { m_type = jtBOOL; m_bv = v; }
    void Set(long v)   { m_type = jtINT;  m_iv = v; }
    void Set(double v) { m_type = jtDBL;  m_dv = v; }
    void Set(string v) { m_type = jtSTR;  m_sv = v; }

    // ── Serialize to JSON string ─────────────────────────────────────
    string Serialize()
    {
        string result = "";
        switch (m_type)
        {
            case jtNULL:  result = "null"; break;
            case jtBOOL:  result = m_bv ? "true" : "false"; break;
            case jtINT:   result = IntegerToString(m_iv); break;
            case jtDBL:   result = DoubleToString(m_dv, 8); break;
            case jtSTR:   result = "\"" + EscapeString(m_sv) + "\""; break;
            case jtARRAY:
            {
                result = "[";
                for (int i = 0; i < ArraySize(m_children); i++)
                {
                    if (i > 0) result += ",";
                    result += m_children[i].Serialize();
                }
                result += "]";
                break;
            }
            case jtOBJ:
            {
                result = "{";
                for (int i = 0; i < ArraySize(m_children); i++)
                {
                    if (i > 0) result += ",";
                    result += "\"" + EscapeString(m_children[i].m_key) + "\":" +
                              m_children[i].Serialize();
                }
                result += "}";
                break;
            }
            default: result = "null"; break;
        }
        return result;
    }

    // ── Deserialize from JSON string ─────────────────────────────────
    bool Deserialize(string json)
    {
        Clear();
        int pos = 0;
        return _Parse(json, pos);
    }

    // ── File helpers ─────────────────────────────────────────────────
    bool ReadFromFile(string filepath)
    {
        int fileHandle = FileOpen(filepath, FILE_READ | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_COMMON);
        if (fileHandle == INVALID_HANDLE)
        {
            fileHandle = FileOpen(filepath, FILE_READ | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
            if (fileHandle == INVALID_HANDLE)
                return false;
        }
        string content = "";
        while (!FileIsEnding(fileHandle))
            content += FileReadString(fileHandle);
        FileClose(fileHandle);
        return Deserialize(content);
    }

    bool WriteToFile(string filepath)
    {
        int fileHandle = FileOpen(filepath, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_COMMON);
        if (fileHandle == INVALID_HANDLE)
        {
            fileHandle = FileOpen(filepath, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
            if (fileHandle == INVALID_HANDLE)
                return false;
        }
        FileWriteString(fileHandle, Serialize());
        FileClose(fileHandle);
        return true;
    }

private:
    // ── Escape special chars ─────────────────────────────────────────
    string EscapeString(string s)
    {
        string r = s;
        StringReplace(r, "\\", "\\\\");
        StringReplace(r, "\"", "\\\"");
        StringReplace(r, "\n", "\\n");
        StringReplace(r, "\r", "\\r");
        StringReplace(r, "\t", "\\t");
        return r;
    }

    // ── Skip whitespace ──────────────────────────────────────────────
    void _SkipWS(const string &json, int &pos)
    {
        int len = StringLen(json);
        while (pos < len)
        {
            ushort ch = StringGetCharacter(json, pos);
            if (ch != ' ' && ch != '\t' && ch != '\n' && ch != '\r')
                break;
            pos++;
        }
    }

    // ── Parse value ──────────────────────────────────────────────────
    bool _Parse(const string &json, int &pos)
    {
        _SkipWS(json, pos);
        if (pos >= StringLen(json)) return false;

        ushort ch = StringGetCharacter(json, pos);
        if (ch == '{')      return _ParseObject(json, pos);
        if (ch == '[')      return _ParseArray(json, pos);
        if (ch == '"')      return _ParseString(json, pos);
        if (ch == 't' || ch == 'f') return _ParseBool(json, pos);
        if (ch == 'n')      return _ParseNull(json, pos);
        return _ParseNumber(json, pos);
    }

    bool _ParseObject(const string &json, int &pos)
    {
        m_type = jtOBJ;
        pos++; // skip '{'
        _SkipWS(json, pos);
        if (pos < StringLen(json) && StringGetCharacter(json, pos) == '}')
        { pos++; return true; }

        while (pos < StringLen(json))
        {
            _SkipWS(json, pos);
            // Read key
            if (StringGetCharacter(json, pos) != '"') return false;
            pos++;
            string key = "";
            while (pos < StringLen(json) && StringGetCharacter(json, pos) != '"')
            {
                if (StringGetCharacter(json, pos) == '\\') pos++;
                key += ShortToString(StringGetCharacter(json, pos));
                pos++;
            }
            pos++; // skip closing "
            _SkipWS(json, pos);
            if (StringGetCharacter(json, pos) != ':') return false;
            pos++;

            CJAVal *child = new CJAVal();
            child.m_key = key;
            child.m_parent = GetPointer(this);
            if (!child._Parse(json, pos)) { delete child; return false; }
            int sz = ArraySize(m_children);
            ArrayResize(m_children, sz + 1);
            m_children[sz] = child;

            _SkipWS(json, pos);
            if (pos < StringLen(json) && StringGetCharacter(json, pos) == ',')
            { pos++; continue; }
            if (pos < StringLen(json) && StringGetCharacter(json, pos) == '}')
            { pos++; return true; }
            return false;
        }
        return false;
    }

    bool _ParseArray(const string &json, int &pos)
    {
        m_type = jtARRAY;
        pos++;
        _SkipWS(json, pos);
        if (pos < StringLen(json) && StringGetCharacter(json, pos) == ']')
        { pos++; return true; }

        while (pos < StringLen(json))
        {
            CJAVal *child = new CJAVal();
            child.m_parent = GetPointer(this);
            if (!child._Parse(json, pos)) { delete child; return false; }
            int sz = ArraySize(m_children);
            ArrayResize(m_children, sz + 1);
            m_children[sz] = child;

            _SkipWS(json, pos);
            if (pos < StringLen(json) && StringGetCharacter(json, pos) == ',')
            { pos++; continue; }
            if (pos < StringLen(json) && StringGetCharacter(json, pos) == ']')
            { pos++; return true; }
            return false;
        }
        return false;
    }

    bool _ParseString(const string &json, int &pos)
    {
        m_type = jtSTR;
        pos++; // skip opening "
        m_sv = "";
        while (pos < StringLen(json))
        {
            ushort ch = StringGetCharacter(json, pos);
            if (ch == '"') { pos++; return true; }
            if (ch == '\\')
            {
                pos++;
                ushort esc = StringGetCharacter(json, pos);
                if (esc == 'n') m_sv += "\n";
                else if (esc == 'r') m_sv += "\r";
                else if (esc == 't') m_sv += "\t";
                else m_sv += ShortToString(esc);
            }
            else
            {
                m_sv += ShortToString(ch);
            }
            pos++;
        }
        return false;
    }

    bool _ParseBool(const string &json, int &pos)
    {
        m_type = jtBOOL;
        if (StringSubstr(json, pos, 4) == "true")
        { m_bv = true; pos += 4; return true; }
        if (StringSubstr(json, pos, 5) == "false")
        { m_bv = false; pos += 5; return true; }
        return false;
    }

    bool _ParseNull(const string &json, int &pos)
    {
        m_type = jtNULL;
        if (StringSubstr(json, pos, 4) == "null")
        { pos += 4; return true; }
        return false;
    }

    bool _ParseNumber(const string &json, int &pos)
    {
        string num = "";
        bool isFloat = false;
        while (pos < StringLen(json))
        {
            ushort ch = StringGetCharacter(json, pos);
            if ((ch >= '0' && ch <= '9') || ch == '-' || ch == '+' ||
                ch == '.' || ch == 'e' || ch == 'E')
            {
                if (ch == '.' || ch == 'e' || ch == 'E') isFloat = true;
                num += ShortToString(ch);
                pos++;
            }
            else break;
        }
        if (isFloat)
        {
            m_type = jtDBL;
            m_dv = StringToDouble(num);
        }
        else
        {
            m_type = jtINT;
            m_iv = StringToInteger(num);
        }
        return StringLen(num) > 0;
    }
};
//+------------------------------------------------------------------+
