param galleryName string = 'VMImages'

param location string = 'eastus'

resource gallery 'Microsoft.Compute/galleries@2021-10-01' = {
  name: galleryName
  location: location
  properties: {}
  tags: {
    Type: 'VMGallery'
  }
}
