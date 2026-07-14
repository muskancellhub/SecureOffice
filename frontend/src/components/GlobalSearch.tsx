import { Search } from 'lucide-react';
import { useEffect,useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { globalSearch, logSearchClick, type SearchHit } from '../api/searchApi';
import { useAuth } from '../context/AuthContext';

// Maps an action hit's id to the route it opens (Slice 4).
const ACTION_ROUTES: Record<string, string> = {
    'action:create-design': '/shop/designs/new',
};

export function GlobalSearch() {
    const { accessToken } = useAuth();
    const navigate = useNavigate();
    const [hits, setHits] = useState<SearchHit[]>([]);
    const [query, setQuery] = useState('');
    const [open, setOpen] = useState(false);
    

    const seqRef= useRef(0);
  
    useEffect(() => {
        const q= query.trim();

        if(!accessToken || q.length<2){
            setHits([]);
            setOpen(false);
            return;
        }

    const controller= new AbortController();
    const mySeq= ++seqRef.current;

    const timer= setTimeout(async () => {
        try {
            const results= await globalSearch(accessToken, q, controller.signal);

            if(mySeq===seqRef.current){
                setHits(results);
                setOpen(true);
            }
        } catch (error) {
        }
    }, 200);

    return () => {
        clearTimeout(timer);
        controller.abort();
    };
}, [accessToken, query]);

const handleSelect = (hit: SearchHit, position: number) => {
    // Slice 5: log the pick (fire-and-forget) so popularity can learn from it.
    if (accessToken) {
        void logSearchClick(accessToken, {
            query: query.trim(),
            hit_id: hit.id,
            hit_type: hit.type,
            position,
        });
    }
    setOpen(false);

    // Slice 6: the backend supplies a deep-link per hit. Fall back to the
    // legacy per-type routing for older hits without a url.
    const dest =
        hit.url ??
        (hit.type === 'action'
            ? ACTION_ROUTES[hit.id]
            : hit.type === 'product'
                ? `/shop/routers/${hit.id}`
                : undefined);
    if (dest) navigate(dest);
};

return (
    <div className="global-search">
      <div className="global-search-box">
        <input
          type="text"
          value={query}
          placeholder="Search products, orders, and more…"
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => hits.length && setOpen(true)}
          className="global-search-input"
        />
        <button type="button" className="global-search-btn" aria-label="Search">
          <Search size={16} />
        </button>
      </div>

      {open && hits.length > 0 && (
        <ul className="global-search-results">
          {hits.map((hit, index) => (
            <li
              key={hit.id}
              className={`global-search-result${hit.type === 'action' ? ' global-search-result-action' : ''}`}
              onClick={() => handleSelect(hit, index)}
            >
              <div className="global-search-result-title">{hit.title}</div>
              {hit.subtitle && (
                <div className="global-search-result-sub">{hit.subtitle}</div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}