// Central currency naming. Normal (meat) = PrimeMeat, VIP (amber) = Amberium.
export const CURRENCY = {
  normal: { name: "PrimeMeat", short: "PM" },
  vip: { name: "Amberium", short: "AMB" },
};

export const currencyName = (type) => (type === "vip" ? CURRENCY.vip.name : CURRENCY.normal.name);
export const currencyShort = (type) => (type === "vip" ? CURRENCY.vip.short : CURRENCY.normal.short);
