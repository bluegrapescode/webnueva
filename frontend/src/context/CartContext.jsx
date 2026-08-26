import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from "react";

const CartContext = createContext(null);

export function CartProvider({ children }) {
  const [items, setItems] = useState(() => {
    try { return JSON.parse(localStorage.getItem("primal_cart")) || []; } catch { return []; }
  });
  const [open, setOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem("primal_cart", JSON.stringify(items));
  }, [items]);

  const add = useCallback((item) => {
    setItems((prev) => {
      const existing = prev.find((i) => i.id === item.id);
      if (existing) return prev.map((i) => i.id === item.id ? { ...i, qty: i.qty + 1 } : i);
      return [...prev, { ...item, qty: 1 }];
    });
  }, []);
  const setQty = useCallback((id, qty) => {
    setItems((prev) => qty <= 0 ? prev.filter((i) => i.id !== id) : prev.map((i) => i.id === id ? { ...i, qty } : i));
  }, []);
  const remove = useCallback((id) => setItems((prev) => prev.filter((i) => i.id !== id)), []);
  const clear = useCallback(() => setItems([]), []);
  const has = useCallback((id) => items.some((i) => i.id === id), [items]);

  const totals = useMemo(() => {
    return items.reduce((acc, i) => {
      const key = i.currency === "vip" ? "vip" : "normal";
      acc[key] += (i.price || 0) * (i.qty || 1);
      return acc;
    }, { normal: 0, vip: 0 });
  }, [items]);

  const count = useMemo(() => items.reduce((n, i) => n + (i.qty || 1), 0), [items]);

  return (
    <CartContext.Provider value={{ items, add, setQty, remove, clear, has, count, totals, open, setOpen }}>
      {children}
    </CartContext.Provider>
  );
}

export const useCart = () => useContext(CartContext);
