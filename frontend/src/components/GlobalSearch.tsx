import { Search } from 'lucide-react';
import { useEffect,useRef, useState } from 'react';
import { globalSearch, type SearchHit } from '../api/searchApi';
import { useAuth } from '../context/AuthContext';

export function GlobalSearch() {
    const { accessToken } = useAuth();
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
          {hits.map((hit) => (
            <li
              key={hit.id}
              className="global-search-result"
              onClick={() => {
                // Slice 1: just log. Later this navigates to the product page
                // or fires the matched action.
                console.log('selected', hit);
                setOpen(false);
              }}
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