/* eslint-disable @next/next/no-img-element */
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { ShoppingCart, Star } from "lucide-react"

export interface Product {
  id: number
  title: string
  price: number
  category?: string
  image?: string
  description?: string
  rating?: { rate: number; count: number } | string
}

interface ProductCardProps {
  product: Product
  onAddToCart?: (productId: number, productTitle: string) => void
}

export function ProductCard({ product, onAddToCart }: ProductCardProps) {
  const ratingValue = typeof product.rating === "string"
    ? parseFloat(product.rating)
    : product.rating?.rate

  const ratingDisplay = typeof product.rating === "string"
    ? product.rating
    : product.rating
      ? `${product.rating.rate} (${product.rating.count})`
      : null

  return (
    <Card className="overflow-hidden hover:shadow-lg hover:border-primary/20 transition-all duration-200 group">
      {product.image && (
        <div className="h-40 bg-gradient-to-b from-slate-50 to-white flex items-center justify-center p-4">
          <img
            src={product.image}
            alt={product.title}
            className="max-h-full max-w-full object-contain group-hover:scale-105 transition-transform duration-200"
          />
        </div>
      )}
      <CardContent className="p-3.5">
        <h3 className="font-medium text-sm line-clamp-2 mb-1.5">{product.title}</h3>
        <div className="flex items-center justify-between mb-2">
          <span className="text-lg font-bold text-primary">
            ${product.price.toFixed(2)}
          </span>
          {ratingValue && ratingDisplay && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Star className="w-3.5 h-3.5 fill-yellow-400 text-yellow-400" />
              {ratingDisplay}
            </div>
          )}
        </div>
        {product.category && (
          <span className="inline-block text-xs text-muted-foreground bg-secondary px-2 py-0.5 rounded-full capitalize mb-2">
            {product.category}
          </span>
        )}
        {product.description && (
          <p className="text-xs text-muted-foreground line-clamp-2 mb-2.5">{product.description}</p>
        )}
        {onAddToCart && (
          <Button
            size="sm"
            className="w-full text-xs rounded-lg"
            onClick={() => onAddToCart(product.id, product.title)}
          >
            <ShoppingCart className="w-3 h-3 mr-1.5" />
            Add to Cart
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
