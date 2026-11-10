import CityClient from "./CityClient";

const CITY_SLUGS = [
  "chengdu", "chongqing", "mianyang", "deyang", "suining", "nanchong",
  "guangan", "ziyang", "meishan", "leshan", "neijiang", "zigong",
  "yibin", "luzhou",
];

export const dynamicParams = false;

export function generateStaticParams() {
  return CITY_SLUGS.map(slug => ({ slug }));
}

export default function CityPage() {
  return <CityClient />;
}
